# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from card.company import single_company, validate_equipment_company
from card.settings import setting
from card.transfer import apply_transfer, check_cancel_allowed, reverse_transfer


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
		for row in self.items:
			validate_equipment_company(frappe._dict(company=self.company, equipment=row.card_equipment))
		self._detect_movements()
		self._validate_project_company()
		self._apply_cost_bearer()
		self._apply_destination_cost_center()
		self._apply_transport_price()
		self._split_amount()

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

	def _apply_destination_cost_center(self):
		"""Owner 2026-10-19: a move is always charged to where the equipment goes — the
		destination project's cost center, or the workshop/storage place's cost center from
		Card Settings (per company: a Location is not company-bound). A return to the
		supplier stays on the project it leaves. Only needed when the company pays."""
		self.cost_center = None
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
			if not self.cost_center and self.cost_borne_by == "Company":
				frappe.throw(
					_(
						"Set the cost center of {0} for company {1} in Card Settings (Transport) before charging a move there."
					).format(self.destination_location, self.company)
				)
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
	def on_submit(self):
		# Transport = a location transfer: move the equipment to the new project.
		apply_transfer(self)

	def before_cancel(self):
		# Guards run before docstatus flips, so a block keeps the doc submitted.
		check_cancel_allowed(self)

	def on_cancel(self):
		reverse_transfer(self)


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
