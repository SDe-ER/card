# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, getdate

from card.company import single_company, validate_equipment_company
from card.constants import OWNED
from card.settings import setting
from card.transfer import apply_transfer, check_cancel_allowed, reverse_transfer

# P1-2 (Owner decisions 2026-10-31): the user picks one responsibility scenario; the actual payer and the
# party that finally bears the cost are stored apart from it (input simplification, Owner 2026-10-31)
NEEDS_REVIEW = "Responsibility needs review"
RESPONSIBILITIES = {
	# scenario -> (payer, cost bearer)
	"Company bears the cost": ("Company", "Company"),
	"Company pays, bills the customer": ("Company", "Customer"),
	"Company pays, recovers from equipment supplier": ("Company", "Equipment Supplier"),
	"Equipment supplier bears the cost": ("Equipment Supplier", "Equipment Supplier"),
	"Customer pays the transporter directly": ("Customer", "Customer"),
	"No transport charge": ("No charge", None),
	NEEDS_REVIEW: (None, None),  # unknown or unsupported: recorded, never costed or posted
}
RESPONSIBILITY_BY_PAIR = {pair: name for name, pair in RESPONSIBILITIES.items() if name != NEEDS_REVIEW}
# recorded only by the financial decision action, never by a save of the submitted transport
FINANCIAL_FIELDS = (
	"financial_status",
	"financial_decision",
	"customer",
	"billing_project",
	"billing_amount",
	"billing_mode",
	"billing_reference",
	"billing_document",
	"absorption_reason",
	"recovery_mode",
	"recovery_amount",
	"decision_note",
	"financial_approver",
	"financial_decided_on",
)
DECISIONS = {
	# cost bearer -> the decisions the Accounts Manager may record
	"Customer": ("Bill customer", "Company absorbs", "Return for correction"),
	"Equipment Supplier": ("Recover from equipment supplier", "Return for correction"),
}


@frappe.whitelist(methods=["GET"])
def get_equipment_location(equipment: str):
	"""The current place of one machine, shown in the transport form as soon as it is picked."""
	from card.transfer import current_location

	frappe.get_doc("Card Equipment", equipment).check_permission("read")
	return current_location(equipment)


class EquipmentTransport(Document):
	def validate(self):
		if not self.company:
			self.company = single_company()  # F.8: default to THE company
		self._sync_items()
		self._default_ownership()
		for row in self.items:
			validate_equipment_company(frappe._dict(company=self.company, equipment=row.card_equipment))
		self._detect_movements()
		self._validate_project_company()
		self._resolve_responsibility()
		if self.responsibility:
			self._apply_cost_responsibility()
		else:
			self._apply_cost_bearer()  # a transport recorded before P1-2 keeps its old rule
		self._apply_destination_cost_center()
		self._apply_transport_price()
		self._split_amount()
		if self.payer == "Company" and flt(self.amount) <= 0:
			frappe.throw(_("Enter the transporter cost of a move the company pays."))
		self.customer_billable = int(self.payer == "Company" and self.cost_bearer == "Customer")
		self.supplier_recoverable = int(self.payer == "Company" and self.cost_bearer == "Equipment Supplier")
		if not self.responsibility or self.responsibility == NEEDS_REVIEW:
			self.financial_status = None
		else:
			self.financial_status = (
				"Pending" if self.customer_billable or self.supplier_recoverable else "No decision needed"
			)
		self._record_editor()

	def _record_editor(self):
		"""Everyone who saves the draft is kept (from the stored value, never from the client): none of them
		records the transport's financial decision (separation of duties)."""
		stored = "" if self.is_new() else frappe.db.get_value(self.doctype, self.name, "edited_by") or ""
		editors = [e for e in stored.split("\n") if e]
		if frappe.session.user not in editors:
			editors.append(frappe.session.user)
		self.edited_by = "\n".join(editors)

	def _resolve_responsibility(self):
		"""The responsibility scenario sets the payer and the cost bearer. A client that sends the
		payer and bearer pair (API, older forms) gets the matching scenario; an unsupported pair is refused."""
		if not self.responsibility and self.payer:
			self.responsibility = RESPONSIBILITY_BY_PAIR.get((self.payer, self.cost_bearer or None))
			if not self.responsibility:
				frappe.throw(
					_(
						"A move paid by {0} with the cost borne by {1} is not supported. When the equipment supplier transports the machine and charges the company, record the company as payer and the equipment supplier as the transporter."
					).format(_(self.payer), _(self.cost_bearer or ""))
				)
		if not self.responsibility:
			return
		if self.responsibility not in RESPONSIBILITIES:
			frappe.throw(_("Select the transport responsibility."))
		self.payer, self.cost_bearer = RESPONSIBILITIES[self.responsibility]

	def _detect_movements(self):
		"""Owner 2026-10-19: the user picks the equipment and the destination (project,
		workshop, storage, or back to the supplier); where each machine is now is read from
		its open assignment or its last approved transport (card.transfer.current_location),
		never typed. A move to where the machine already is is refused, except a move to
		another site of the same project (To filled in)."""
		from card.transfer import current_location

		destination = self.destination_type or "Project"
		self.destination_type = destination
		if destination != "Project":
			# the project left is kept per row (from_project); a supplier return sets it below
			self.project = None
		if destination not in ("Workshop", "Storage"):
			self.destination_location = None
		sources = set()
		for row in self.items:
			here = current_location(row.card_equipment, exclude=self.name)
			row.from_type, row.from_project, row.from_location = here.type, here.project, here.location
			if here.project:
				sources.add(here.project)
			if destination == "Project":
				if here.type == "Project" and here.project == self.project:
					# Owner 2026-10-19: To is an ERPNext project, never typed text, so a
					# move to the project the machine is already on is no move at all
					frappe.throw(
						_("Equipment {0} is already on project {1}.").format(row.card_equipment, self.project)
					)
				else:
					row.movement = (
						"First entry" if here.get("initial") or here.type == "Supplier" else "Transfer"
					)
				continue
			if here.type == destination and (
				destination == "Supplier" or here.location == self.destination_location
			):
				frappe.throw(_("Equipment {0} is already there.").format(row.card_equipment))
			if (
				destination == "Supplier"
				and frappe.db.get_value("Card Equipment", row.card_equipment, "ownership") == "ملك"
			):
				frappe.throw(
					_("Equipment {0} is owned; only rented equipment returns to a supplier.").format(
						row.card_equipment
					)
				)
			row.movement = {
				"Workshop": "To workshop",
				"Storage": "To storage",
				"Supplier": "Return to supplier",
			}[destination]
		# the header "From" shows the first machine's place (each row keeps its own)
		first = self.items[0] if self.items else None
		self.source_type = first.from_type if first else None
		self.source_project = first.from_project if first else None
		self.source_location = first.from_location if first else None
		if destination == "Supplier":
			# Owner 2026-10-19: a return to the supplier is charged to the project it leaves
			if len(sources) > 1:
				frappe.throw(
					_(
						"These machines come from different projects ({0}); record one transport per project."
					).format(", ".join(sorted(sources)))
				)
			self.project = sources.pop() if sources else None

	def _validate_project_company(self):
		"""P0 D3 (Owner 2026-10-20): the project a transport goes to (or, for a return to
		the supplier, the project it leaves) belongs to the transport's company, as every
		machine in it does; otherwise the move would take another company's cost center."""
		if not self.project:
			return
		project_company = frappe.db.get_value("Project", self.project, "company")
		if project_company and project_company != self.company:
			frappe.throw(
				_("Project {0} belongs to company {1}; this transport belongs to company {2}.").format(
					self.project, project_company, self.company
				)
			)

	def _apply_cost_responsibility(self):
		"""P1-2 (Owner decisions 2026-10-31): where the company's own cost is charged is explicit — the
		chosen cost project, or the workshop/storage place a move goes to — never the origin or the
		destination project. Only a move whose cost the company finally bears is charged anywhere."""
		self.cost_borne_by = None  # the old mixed field stays only on transports recorded before P1-2
		if self.payer != "Company":
			# no transporter cost for the company, or responsibility unknown (needs review): nothing to
			# charge anywhere
			self.cost_basis = self.cost_project = self.overhead_cost_center = None
			self.amount = 0
			for row in self.items:
				row.amount, row.manual_share = 0, 0
			return
		if not self.transport_supplier:
			frappe.throw(_("Select the transporter of a move the company pays."))
		if self.cost_bearer != "Company":
			# recharged to the customer or the equipment supplier: decided by the Accounts Manager
			self.cost_basis = self.cost_project = self.overhead_cost_center = None
			return
		if self.destination_type in ("Workshop", "Storage"):
			self.cost_basis, self.cost_project, self.overhead_cost_center = "Workshop or storage", None, None
		elif self.cost_project or not self.overhead_cost_center:
			self.cost_basis, self.overhead_cost_center = "Project", None
			self._check_cost_project()
		else:
			# an overhead cost center sent by an API client (not offered on the form)
			self.cost_basis, self.cost_project = "Company overhead", None
			self._check_cost_center(self.overhead_cost_center)

	def _check_cost_project(self):
		if not self.cost_project:
			frappe.throw(
				_(
					"Select the cost project. It is never taken from where the machine comes from or goes to; choose it explicitly."
				)
			)
		project = frappe.db.get_value("Project", self.cost_project, ["company", "cost_center"], as_dict=True)
		if not project or project.company != self.company:
			frappe.throw(
				_("Cost project {0} does not belong to company {1}.").format(self.cost_project, self.company)
			)
		if not project.cost_center:
			frappe.throw(
				_("Cost project {0} has no cost center; set the project's cost center first.").format(
					self.cost_project
				)
			)
		self._check_cost_center(project.cost_center)

	def _check_cost_center(self, cost_center):
		from card.gl.posting import _valid_cost_center

		if not _valid_cost_center(cost_center, self.company):
			frappe.throw(
				_(
					"Cost center {0} cannot carry a cost of company {1} (it must be an enabled, non-group cost center of that company)."
				).format(cost_center, self.company)
			)

	def _apply_destination_cost_center(self):
		"""Owner 2026-10-19: a move is always charged to where the equipment goes — the
		destination project's cost center, or the workshop/storage place's cost center from
		Card Settings (per company: a Location is not company-bound). A return to the
		supplier stays on the project it leaves. Only needed when the company pays.
		P1-2: a transport with a recorded payer takes the cost center of its explicit choice
		instead (cost project, place, or overhead cost center); none when the company pays nothing."""
		self.cost_center = None
		if self.responsibility:
			if (self.payer, self.cost_bearer) != ("Company", "Company"):
				return
			if self.cost_basis == "Project":
				self.cost_center = frappe.db.get_value("Project", self.cost_project, "cost_center")
				return
			if self.cost_basis == "Company overhead":
				self.cost_center = self.overhead_cost_center
				return
		if self.destination_type in ("Workshop", "Storage"):
			self.cost_center = frappe.db.get_value(
				"Card Location Cost Center",
				{
					"parent": "Card Settings",
					"parenttype": "Card Settings",
					"company": self.company,
					"location": self.destination_location,
				},
				"cost_center",
			)
			if not self.cost_center and (
				self.payer == "Company" or (not self.payer and self.cost_borne_by == "Company")
			):
				frappe.throw(
					_(
						"Set the cost center of {0} for company {1} in Card Settings (Transport) before charging a move there."
					).format(self.destination_location, self.company)
				)
			if self.cost_center and self.payer == "Company":
				self._check_cost_center(self.cost_center)
		elif self.project:
			self.cost_center = frappe.db.get_value("Project", self.project, "cost_center")

	def _apply_cost_bearer(self):
		"""Owner decision 2026-10-19: who pays the move. Company: the transport supplier bills
		us (Purchase Invoice, as before). Equipment Supplier: no cost for us, no invoice.
		Customer: the cost is recorded for follow-up only; how it is charged is decided later."""
		if not self.cost_borne_by:
			self.cost_borne_by = "Company"
		if self.cost_borne_by == "Equipment Supplier":
			self.amount = 0
			for row in self.items:
				row.amount, row.manual_share = 0, 0

	def _sync_items(self):
		"""v3.0.0: the equipment table is the source; the header `equipment` mirrors its
		first row for links and older readers. A caller that still sets only the header
		(older API/tests) gets it moved into the table."""
		before = None if self.is_new() else self.get_doc_before_save()
		if not before or before.docstatus == 0:
			# only on_submit writes these (card.transfer). A draft, and the submit itself
			# (validate runs with docstatus 1 and the client's values), must not carry links
			# typed through the API, or a later cancel would delete/reopen another assignment
			self.previous_assignment = self.created_assignment = None
			for row in self.items:
				row.previous_assignment = row.created_assignment = None
		if not self.items and self.equipment:
			self.append("items", {"card_equipment": self.equipment})
		seen = set()
		for row in self.items:
			if row.card_equipment in seen:
				frappe.throw(_("Equipment {0} is listed twice in this transport.").format(row.card_equipment))
			seen.add(row.card_equipment)
		self.equipment = self.items[0].card_equipment if self.items else None

	def _default_ownership(self):
		"""v4.1.2: ownership and the equipment supplier are read from the first machine when
		the user (or an older API caller) left them empty; a value typed in is kept."""
		if not self.items or (self.ownership and (self.ownership == OWNED or self.equipment_supplier)):
			return
		ownership, supplier = frappe.db.get_value(
			"Card Equipment", self.items[0].card_equipment, ["ownership", "supplier"]
		) or (None, None)
		self.ownership = self.ownership or ownership
		if self.ownership and self.ownership != OWNED and not self.equipment_supplier:
			self.equipment_supplier = supplier

	def _split_amount(self):
		"""Owner decision 2026-10-18: the trip cost is split equally over the equipment;
		any share may be edited, but the shares must add up to the trip cost. A share typed
		by hand is remembered (`manual_share`) and kept; every other share is recomputed
		on each save from what the typed ones leave, so editing one share or the trip
		cost rebalances the rest. Clearing a share hands it back to the equal split."""
		if not self.items:
			return
		total = flt(self.amount, 2)
		before = self.get_doc_before_save()
		previous = {r.name: flt(r.amount, 2) for r in (before.get("items") or [])} if before else {}
		for row in self.items:
			amount = flt(row.amount, 2)
			if not amount:
				row.manual_share = 0
			elif before is None or previous.get(row.name) != amount:
				row.manual_share = 1  # typed now (a new document's rows count as typed)
			if not row.manual_share:
				row.amount = 0
		self._fill_empty_shares(total)
		shares = self._shares()
		if shares != total:
			frappe.throw(
				_("The equipment cost shares add up to {0}, but the transport cost is {1}.").format(
					shares, total
				)
			)
		for row in self.items:
			if flt(row.amount) < 0:
				frappe.throw(_("A cost share cannot be negative ({0}).").format(row.card_equipment))

	def _shares(self):
		return flt(sum(flt(r.amount, 2) for r in self.items), 2)

	def _fill_empty_shares(self, total):
		empty = [row for row in self.items if not flt(row.amount)]
		if not empty:
			return
		remaining = flt(total - self._shares(), 2)
		share = flt(remaining / len(empty), 2)
		for row in empty:
			row.amount = share
		# rounding cents go to the last empty row so the shares add up exactly
		empty[-1].amount = flt(remaining - share * (len(empty) - 1), 2)

	def _apply_transport_price(self):
		"""F.1: the amount defaults from the Settings per-project price table;
		changing a configured price needs the permitted role. Projects without a
		row keep free manual entry. Historical docs resaved unchanged pass."""
		if not self.project or self.cost_borne_by == "Equipment Supplier":
			return
		if self.responsibility and self.payer != "Company":
			return
		rows = frappe.get_all(
			"Card Project Transport Price",
			filters={"parent": "Card Settings", "project": self.project},
			fields=["amount"],
			limit=1,
			parent_doctype="Card Settings",
		)
		if not rows:
			return
		configured = flt(rows[0].amount)
		if not flt(self.amount):
			self.amount = configured
			return
		if flt(self.amount) == configured:
			return
		before = self.get_doc_before_save()
		# "unchanged" only counts for the SAME project: switching an amount typed
		# under free entry onto a configured project must re-pass the role gate.
		if (
			before is not None
			and flt(before.get("amount")) == flt(self.amount)
			and before.get("project") == self.project
		):
			return
		role = setting("transport_price_editor_role") or "Card Manager"
		if frappe.session.user != "Administrator" and role not in frappe.get_roles():
			frappe.throw(
				_(
					"Only users with role {0} may change the transport amount for project {1} (configured: {2})."
				).format(role, self.project, configured)
			)

	# The accounting posting (Purchase Invoice to the transport supplier, cost on the
	# project) is added in a later stage, gated by owner approval.
	def before_submit(self):
		# P1-2 separation of duties: whoever submits a transport never records its financial decision
		self.submitted_by = frappe.session.user

	def on_submit(self):
		# Transport = a location transfer: move the equipment to the new project.
		apply_transfer(self)

	def before_update_after_submit(self):
		"""The financial decision is recorded only by record_financial_decision (Accounts
		Manager, separation of duties); a save of the submitted transport cannot change it."""
		before = self.get_doc_before_save()
		if before and any(cstr(self.get(f)) != cstr(before.get(f)) for f in FINANCIAL_FIELDS):
			frappe.throw(_("The financial decision of a transport is recorded by an Accounts Manager only."))

	def before_cancel(self):
		# Guards run before docstatus flips, so a block keeps the doc submitted.
		self._refuse_changes_on_cancel()
		check_cancel_allowed(self)

	def _refuse_changes_on_cancel(self):
		"""A cancel runs no validate and stores the values the request sent (frappe
		Document._save, action "cancel"), so a cancel sent as a save with docstatus 2 could
		rewrite the machines and assignment links that reverse_transfer undoes. Only the
		transport as approved is cancelled."""
		if _cancel_key(self) != _cancel_key(self.get_latest()):
			frappe.throw(
				_(
					"Transport {0} is cancelled as approved; its details cannot be changed when cancelling."
				).format(self.name)
			)

	def on_cancel(self):
		reverse_transfer(self)


def _cancel_key(doc):
	"""What a cancel reads (card.transfer) and keeps on the cancelled transport, in one
	comparable form (a request sends dates and numbers as text)."""
	return (
		cstr(doc.company),
		cstr(getdate(doc.date)) if doc.date else "",
		cstr(doc.project),
		cstr(doc.destination_type),
		cstr(doc.destination_location),
		flt(doc.amount, 2),
		[
			(
				cstr(row.name),
				cstr(row.card_equipment),
				cstr(row.created_assignment),
				cstr(row.previous_assignment),
				flt(row.amount, 2),
			)
			for row in doc.get("items") or []
		],
	)


# P0 company isolation D3 (Owner 2026-10-20): Frappe checks create/write permission on
# the values the client sends (frappe/model/document.py: insert, _save), so a user of
# company A could send company A for a company-B draft transport, or leave the company
# empty and let validate default it. The transport's company is checked here.


def has_transport_permission(doc, ptype=None, user=None, debug=False):
	"""Document-level check for every path (read, create, REST/Desk save, set_value,
	submit, cancel): the company sent and, for a saved transport, the company stored in
	the database must be permitted; with no company sent, the companies of the machines,
	of the project and the default company validate would fill in decide. Scope = the
	Company User Permissions that apply to transports, as the transport list uses.
	A read costs one query.
	A controller can only deny (Frappe 16 treats a falsy return as a denial)."""
	from card.party_registry import _restricted_companies

	companies = _restricted_companies(user or frappe.session.user, "Equipment Transport")
	if companies is None:
		return True
	owners = {doc.get("company")}
	if not doc.is_new():
		owners.add(frappe.db.get_value(doc.doctype, doc.name, "company"))
	if not doc.get("company"):
		owners.add(single_company())  # what validate fills in
		equipment = {row.get("card_equipment") for row in doc.get("items") or []} | {doc.get("equipment")}
		equipment.discard(None)
		if equipment:
			owners.update(
				frappe.get_all("Card Equipment", filters={"name": ["in", list(equipment)]}, pluck="company")
			)
		if doc.get("project"):
			owners.add(frappe.db.get_value("Project", doc.project, "company"))
	owners.discard(None)
	owners.discard("")
	return all(company in companies for company in owners)


@frappe.whitelist(methods=["POST"])
def record_financial_decision(
	transport: str,
	decision: str,
	customer: str | None = None,
	billing_project: str | None = None,
	billing_amount: float | None = None,
	billing_mode: str | None = None,
	billing_reference: str | None = None,
	billing_document: str | None = None,
	absorption_reason: str | None = None,
	recovery_mode: str | None = None,
	recovery_amount: float | None = None,
	note: str | None = None,
	confirmed: int | str = 0,
):
	"""P1-2 (Owner D3/D4/D6/D7/D8, 2026-10-31): an Accounts Manager records the financial decision
	of a submitted transport whose cost the customer or the equipment supplier bears — bill the
	customer (agreed amount, authorization), the company absorbs it (documented reason), recover
	it from the equipment supplier, or reject it. Separation of duties: never the transport's
	creator, editor or submitter (nor those of the transport it amends). The decision is only recorded: customer billing, supplier recovery and
	absorption postings stay disabled until the accountant and the tax adviser decide."""
	from frappe.utils import now_datetime

	from card.report_access import permitted_companies

	user = frappe.session.user
	if "Accounts Manager" not in frappe.get_roles(user):
		frappe.throw(
			_("Only an Accounts Manager records the financial decision of a transport."),
			frappe.PermissionError,
		)
	# row lock: two Accounts Managers deciding at once cannot both pass the "Pending" check
	doc = frappe.get_doc("Equipment Transport", transport, for_update=True)
	doc.check_permission("read")
	if doc.company not in permitted_companies("Equipment Transport"):
		frappe.throw(
			_("You are not permitted to view data of company {0}").format(doc.company), frappe.PermissionError
		)
	if doc.docstatus != 1 or doc.financial_status != "Pending":
		frappe.throw(_("Transport {0} has no pending financial decision.").format(doc.name))
	if user in _transport_authors(doc):
		frappe.throw(
			_(
				"The financial decision of transport {0} is recorded by another person than its creator or submitter."
			).format(doc.name),
			frappe.PermissionError,
		)
	if decision not in DECISIONS.get(doc.cost_bearer, ()):
		frappe.throw(
			_("Decision {0} does not fit a transport whose cost is borne by {1}.").format(
				_(decision), _(doc.cost_bearer)
			)
		)

	values = dict.fromkeys(FINANCIAL_FIELDS)
	values.update(
		billing_amount=0,  # Currency columns are NOT NULL
		recovery_amount=0,
		financial_decision=decision,
		decision_note=(note or "").strip() or None,
		financial_approver=user,
		financial_decided_on=now_datetime(),
		financial_status="Rejected" if decision == "Return for correction" else "Approved",
	)
	if decision == "Bill customer":
		values.update(
			_billing_values(
				doc,
				customer,
				billing_project,
				billing_amount,
				billing_mode,
				billing_reference,
				billing_document,
				confirmed,
			)
		)
	elif decision == "Company absorbs":
		if not (absorption_reason or "").strip():
			frappe.throw(_("Write why the company absorbs the customer's transport cost."))
		values["absorption_reason"] = absorption_reason.strip()
	elif decision == "Recover from equipment supplier":
		recovery_mode = recovery_mode or "Deduct from monthly dues"
		if recovery_mode not in ("Deduct from monthly dues", "Adjustment document"):
			frappe.throw(_("Select how the cost is recovered from the equipment supplier."))
		if flt(recovery_amount) <= 0:
			frappe.throw(_("Enter the amount recovered from the equipment supplier."))
		values.update(recovery_mode=recovery_mode, recovery_amount=flt(recovery_amount, 2))
	elif not values["decision_note"]:
		frappe.throw(_("Write why the transport is rejected."))
	# the gate above (role, record read, company, separation of duties) is the authorization; the
	# fields are read-only and refused on any save of the submitted transport (before_update_after_submit)
	before = doc.financial_status
	doc.db_set(values)
	_audit_status_change(doc, before, values["financial_status"])
	# no decision value: the decision, amounts, customer and reasons are permlevel-1 fields, and a comment
	# is visible to every reader of the transport (approver and time stay in the decision fields)
	doc.add_comment("Info", _("Financial decision recorded."))
	return {"financial_status": values["financial_status"], "financial_decision": decision}


@frappe.whitelist(methods=["GET"])
def billing_customer(transport: str, project: str | None = None):
	"""The billing project suggested for a transport's financial decision (its destination project, when
	that project names a customer) or the customer of the project the accountant picks — read only, for
	an Accounts Manager who may read the transport; the project must belong to the transport's company.
	The accountant confirms both before the decision is recorded."""
	if "Accounts Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only an Accounts Manager records the financial decision of a transport."),
			frappe.PermissionError,
		)
	doc = frappe.get_doc("Equipment Transport", transport)
	doc.check_permission("read")
	if not project and doc.destination_type == "Project":
		project = doc.project
	row = (
		frappe.db.get_value("Project", project, ["company", "customer", "status"], as_dict=True)
		if project
		else None
	)
	if not row or row.company != doc.company or row.status == "Cancelled" or not row.customer:
		return {}
	return {"project": project, "customer": row.customer}


def _audit_status_change(doc, before, after):
	"""The decision is written with db_set (no save of the submitted transport), so its change is
	recorded as a Version here. Only the level-0 status goes into it: Versions reach every reader
	of the transport, and the decision values are permlevel-1 fields (write-once, with the
	approver and the time)."""
	version = frappe.new_doc("Version")
	version.ref_doctype, version.docname = doc.doctype, doc.name
	version.data = frappe.as_json(
		{"changed": [["financial_status", before, after]], "added": [], "removed": [], "row_changed": []},
		indent=None,
	)
	version.insert(ignore_permissions=True)  # an audit record of an authorized action, as frappe does


def _transport_authors(doc):
	"""Who created, edited or submitted the transport, or a transport it amends: none of them records
	its financial decision (separation of duties)."""
	authors, source = set(), doc.name
	while source:
		row = frappe.db.get_value(
			"Equipment Transport", source, ["owner", "submitted_by", "edited_by", "amended_from"]
		)
		if not row:
			break
		authors.update(row[:2])
		authors.update((row[2] or "").split("\n"))
		source = row[3]
	return authors - {None, ""}


def _billing_values(
	doc,
	customer,
	billing_project,
	billing_amount,
	billing_mode,
	billing_reference,
	billing_document,
	confirmed,
):
	project = (
		frappe.db.get_value("Project", billing_project, ["company", "customer", "status"], as_dict=True)
		if billing_project
		else None
	)
	if not project or project.company != doc.company or project.status == "Cancelled":
		frappe.throw(_("Select the billing project of company {0}.").format(doc.company))
	customer = customer or project.customer  # the project's own customer, shown to the accountant
	if not customer or not frappe.db.exists("Customer", {"name": customer, "disabled": 0}):
		frappe.throw(_("Select an active customer to bill."))
	frappe.has_permission("Customer", "read", customer, throw=True)
	if not cint(confirmed):
		frappe.throw(_("Confirm the customer and the billing project."))
	if project.customer and project.customer != customer:
		frappe.throw(
			_("Project {0} belongs to customer {1}, not {2}.").format(
				billing_project, project.customer, customer
			)
		)
	if flt(billing_amount) <= 0:
		frappe.throw(_("Enter the agreed billing amount."))
	if not (billing_reference or "").strip():
		frappe.throw(_("Enter the authorization reference (contract, order or approval)."))
	billing_mode = billing_mode or "Monthly invoice"
	if billing_mode not in ("Monthly invoice", "Separate invoice"):
		frappe.throw(_("Select whether the customer is billed on the monthly invoice or separately."))
	if billing_document and not any(
		frappe.has_permission("File", "read", name)
		for name in frappe.get_all("File", filters={"file_url": billing_document}, pluck="name")
	):
		# several File rows can share one URL (same content); one the user may read is enough
		frappe.throw(_("The authorization document was not found."))
	if billing_mode == "Separate invoice" and not billing_document:
		frappe.throw(_("Attach the authorization document of a separate invoice."))
	return {
		"customer": customer,
		"billing_project": billing_project,
		"billing_amount": flt(billing_amount, 2),
		"billing_mode": billing_mode,
		"billing_reference": billing_reference.strip(),
		"billing_document": billing_document or None,
	}
