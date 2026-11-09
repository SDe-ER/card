# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import hashlib
import re
import unicodedata

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Sum, UnixTimestamp
from frappe.utils import add_days, cint, cstr, flt, getdate

from card.constants import (
	CUSTOMER_BILLING_DIRECTIONS,
	OWNED,
	SUPPLIER_BILLING_DIRECTIONS,
	allowed_directions,
	derive_direction,
)
from card.dimension import ASSET_LINK_FIELD, sync_asset_dimension
from card.settings import setting

# Commercial terms: permlevel 1 (Card Manager writes, Card User reads) and every
# change needs a reason, recorded with the change in the document history.
COMMERCIAL_FIELDS = (
	"ownership",
	"supplier",
	"rental_start_date",
	"rental_end_date",
	"contract_no",
	"rate_type",
	"rate",
	"daily_hours",
	"الوقود_على",
	"internal_hourly_rate",
	"customer_rate_type",
	"customer_rate",
	"customer_rate_night",
	"default_customer",
	"rental_direction",
	"operator_on",
)

# #56: documents whose company follows the equipment's; once one exists the
# equipment's company is fixed (cards, postings and reports keep their company)
COMPANY_BOUND_REFERENCES = (
	("Card Monthly Card", "equipment"),
	("Card Equipment Assignment", "equipment"),
	("Project Diesel Fill", "card_equipment"),
	("Equipment Transport", "equipment"),
	("Equipment Transport Item", "card_equipment"),
	("Card Equipment Component", "component"),
	("Card Equipment Part", "card_equipment"),  # FR-077: fitment rows keep their company
)

# D1: a chassis or plate number belongs to one equipment per company; the key
# field holds the comparable form of the number
IDENTITY_FIELDS = (("serial_no", "serial_no_key"), ("plate_no", "plate_no_key"))
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_SEPARATORS = re.compile(r"[\s\-_/.]+")


def identity_key(value):
	"""Comparable form of a chassis or plate number: Unicode NFKC without invisible
	format marks (RLM, ZWJ, ...), Arabic-Indic digits as ASCII, no spaces or
	separators (- _ / .), upper case. None for an empty value."""
	text = unicodedata.normalize("NFKC", cstr(value))
	text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
	key = _SEPARATORS.sub("", text.translate(_DIGITS)).upper()
	return key or None


def on_doctype_update():
	# D1: the duplicate check reads (company, key); a composite index keeps its locking
	# read inside one company's range
	for _field, key_field in IDENTITY_FIELDS:
		frappe.db.add_index("Card Equipment", ["company", key_field])


def _lock_company_identities(company):
	"""Saves that set a number of the same company run one after the other: a MariaDB
	named lock per company, owned by CARD (no ERPNext row is locked), released when
	the transaction ends."""
	name = "card-equipment-identity-" + hashlib.sha1(cstr(company).encode()).hexdigest()[:32]
	if not frappe.db.sql("select get_lock(%s, 10)", (name,))[0][0]:
		frappe.throw(_("Another equipment of company {0} is being saved. Try again.").format(company))

	def release():
		frappe.db.sql("select release_lock(%s)", (name,))

	frappe.db.after_commit.add(release)
	frappe.db.after_rollback.add(release)


def asset_equipment_values(asset):
	"""Details the linked ERPNext Asset holds for its equipment: the name, the Asset
	item's brand and the equipment type mapped to the Asset category. No permission
	check: callers check the Asset first."""
	values = frappe.db.get_value("Asset", asset, ["asset_name", "asset_category", "item_code"], as_dict=True)
	if not values:
		return {}
	return {
		"equipment_name": values.asset_name or asset,
		"brand": values.item_code and frappe.db.get_value("Item", values.item_code, "brand"),
		"equipment_type": values.asset_category
		and frappe.db.get_value("Card Equipment Type", {"asset_category": values.asset_category}, "name"),
	}


class CardEquipment(Document):
	def on_update(self):
		# O3: the linked Asset carries the equipment as its accounting dimension,
		# so depreciation entries land on the equipment in GL. No-op without the dimension.
		sync_asset_dimension(self)
		# WP-05: the pieces that joined or left this unit get their derived component flag
		# (move_component syncs once itself, after both units are saved)
		if not frappe.flags.get("card_defer_unit_flag_sync"):
			before = self.get_doc_before_save()
			pieces = {r.component for r in self.get("components") or [] if r.component}
			pieces.update(
				r.component for r in (before.get("components") if before else None) or [] if r.component
			)
			sync_unit_component_flags(pieces)
		if self.has_value_changed("equipment_model"):
			# FR-077: a machine's fitment rows carry its model (filters, conflict check)
			frappe.db.set_value(
				"Card Equipment Part",
				{"card_equipment": self.name},
				"equipment_model",
				self.equipment_model,
				update_modified=False,
			)

	def on_trash(self):
		# WP-05: a deleted unit's pieces are re-derived once its rows are gone (after_delete)
		self.flags.card_unit_pieces = {r.component for r in self.get("components") or [] if r.component}

	def after_delete(self):
		sync_unit_component_flags(self.flags.get("card_unit_pieces") or ())

	def validate(self):
		self.sync_asset_details()
		self.apply_new_record_defaults()
		self.keep_derived_unit_component()
		self.validate_rental_direction()
		self.validate_commercial_change_reason()
		self.validate_unique_asset()
		self.validate_equipment_model()
		self.set_identity_keys()
		if not (frappe.flags.in_patch or frappe.flags.in_install or frappe.flags.in_migrate):
			self.validate_unique_identity()
			self.keep_derived_location()
			# #56: checked only when the value changes, so a legacy row is never
			# blocked by an unrelated save
			self.validate_company_change()
			self.validate_asset_link()
			self.validate_owned_unit()
			self.validate_components()
		# Ported from Server Script "Card Equipment - Hourly Rate" (Before Validate).
		# Computes the read-only approved_hourly_rate shown on the equipment.
		rate = flt(self.rate)
		if self.rate_type == "باليوم":
			if flt(self.daily_hours) <= 0:
				frappe.throw(_("Set the daily working hours (shift) to calculate the hourly rate"))
			self.approved_hourly_rate = flt(rate / flt(self.daily_hours), 2)
		elif self.rate_type == "بالساعة":
			self.approved_hourly_rate = rate
		elif self.rate_type == "بالشهر":
			# F.5: monthly basis spreads the rate over the standard month hours
			month_hours = flt(setting("standard_month_hours")) or 260
			self.approved_hourly_rate = flt(rate / month_hours, 2)
		else:
			self.approved_hourly_rate = 0

	def sync_asset_details(self):
		"""Owner 2026-10-19: an equipment linked to an Asset takes its details from it
		(read-only on the form; enforced here for REST and imports too)."""
		asset = self.get(ASSET_LINK_FIELD)
		values = asset_equipment_values(asset) if asset else {}
		self.equipment_type_from_asset = 1 if values.get("equipment_type") else 0
		for fieldname, value in values.items():
			if value:
				self.set(fieldname, value)

	def validate_commercial_change_reason(self):
		"""A change to a commercial term of an existing equipment needs a NEW
		reason (enforced server-side, so REST and imports are covered too).
		Migrations and installs are exempt."""
		if self.is_new() or frappe.flags.in_patch or frappe.flags.in_install or frappe.flags.in_migrate:
			return
		before = self.get_doc_before_save()
		if not before:
			return
		changed = [f for f in COMMERCIAL_FIELDS if _differs(before.get(f), self.get(f))]
		if not changed:
			return
		reason = (self.commercial_change_reason or "").strip()
		if not reason or reason == (before.commercial_change_reason or "").strip():
			labels = ", ".join(_(self.meta.get_label(f)) for f in changed)
			frappe.throw(
				_("Enter the reason for changing the commercial terms: {0}").format(labels),
				title=_("Reason required"),
			)

	def validate_equipment_model(self):
		"""FR-077: the model belongs to the machine's make and equipment type; an empty
		make is taken from the model. A disabled make or model is refused only when set."""
		if self.has_value_changed("equipment_make") and self.equipment_make:
			if frappe.db.get_value("Card Equipment Make", self.equipment_make, "disabled"):
				frappe.throw(_("Equipment make {0} is disabled.").format(self.equipment_make))
		if not self.equipment_model:
			return
		model = frappe.db.get_value(
			"Card Equipment Model",
			self.equipment_model,
			["equipment_make", "equipment_type", "disabled"],
			as_dict=True,
		)
		if not model:
			frappe.throw(_("Equipment model {0} does not exist.").format(self.equipment_model))
		if self.has_value_changed("equipment_model") and model.disabled:
			frappe.throw(_("Equipment model {0} is disabled.").format(self.equipment_model))
		if not self.equipment_make:
			self.equipment_make = model.equipment_make
			if frappe.db.get_value("Card Equipment Make", self.equipment_make, "disabled"):
				frappe.throw(_("Equipment make {0} is disabled.").format(self.equipment_make))
		if model.equipment_make == self.equipment_make and model.equipment_type == self.equipment_type:
			return
		if (
			self.is_new()
			or self.has_value_changed("equipment_model")
			or self.has_value_changed("equipment_make")
		):
			frappe.throw(
				_("Equipment model {0} does not belong to this make and equipment type.").format(
					self.equipment_model
				)
			)
		# only the type changed (it follows the linked Asset's category on every save): the
		# model no longer applies. It is cleared instead of blocking every later save, but
		# only by a user who may write it (permlevel 1); for anyone else it stays as stored
		if not self.has_permlevel_access_to("equipment_model", permission_type="write"):
			return
		frappe.msgprint(
			_("Equipment model {0} was cleared: it does not belong to the new equipment type.").format(
				self.equipment_model
			)
		)
		self.equipment_model = None

	def validate_rental_direction(self):
		"""F.7: rental_direction is the single source of truth. A blank one is
		derived from ownership (legacy rows keep working); a chosen one must
		match the ownership; the mandatory party/rate of each direction is
		enforced server-side (depends_on in the form is client-side only)."""
		if not self.rental_direction:
			self.rental_direction = derive_direction(self.ownership)
		if self.rental_direction not in allowed_directions(self.ownership):
			frappe.throw(
				_("Direction {0} is not valid for ownership {1}.").format(
					self.rental_direction, self.ownership
				)
			)
		if self.rental_direction in SUPPLIER_BILLING_DIRECTIONS:
			if not self.supplier:
				frappe.throw(_("Direction {0} requires a supplier.").format(self.rental_direction))
			if not self.rate_type or not flt(self.rate):
				frappe.throw(
					_("Direction {0} requires the supplier rate and its basis.").format(self.rental_direction)
				)
		if self.rental_direction in CUSTOMER_BILLING_DIRECTIONS:
			if not self.default_customer:
				frappe.throw(_("Direction {0} requires a customer.").format(self.rental_direction))
			if not self.customer_rate_type or not flt(self.customer_rate):
				frappe.throw(
					_("Direction {0} requires the customer rate and its basis.").format(self.rental_direction)
				)

	def validate_unique_asset(self):
		# One ERPNext Asset <-> at most one Card Equipment.
		asset = self.get("الأصل_في_erpnext")
		if not asset:
			return
		other = frappe.db.get_value(
			"Card Equipment",
			{"الأصل_في_erpnext": asset, "name": ["!=", self.name or ""]},
			"name",
		)
		if other:
			# name the other equipment only to a user who may read the Asset; an unchanged
			# legacy link is never blocked by an unrelated save
			changed = self.is_new() or self.has_value_changed("الأصل_في_erpnext")
			if changed and not frappe.has_permission("Asset", "read", asset):
				self._refuse_unreadable_asset(asset)
			frappe.throw(_("Asset {0} is already linked to equipment {1}").format(asset, other))

	def set_identity_keys(self):
		for field, key_field in IDENTITY_FIELDS:
			self.set(key_field, identity_key(self.get(field)))

	def validate_unique_identity(self):
		"""D1: a chassis or plate number is used by one equipment per company. Checked
		when the number is set or changed, or the company changes, so an unrelated save
		of a legacy duplicate is never blocked."""
		changed = [
			(field, key_field)
			for field, key_field in IDENTITY_FIELDS
			if self.get(key_field)
			and (self.is_new() or self.has_value_changed(key_field) or self._company_changed())
		]
		if not changed:
			return
		# the second of two saves at once waits here until the first commits; then its
		# locking read below sees the first's row
		_lock_company_identities(self.company)
		equipment = frappe.qb.DocType("Card Equipment")
		for field, key_field in changed:
			rows = (
				frappe.qb.from_(equipment)
				.select(equipment.name)
				.where(equipment.company == self.company)
				.where(getattr(equipment, key_field) == self.get(key_field))
				.where(equipment.name != (self.name or ""))
				.limit(1)
				.for_update()
				.run()
			)
			if not rows:
				continue
			label = _(self.meta.get_label(field))
			other = rows[0][0]
			if frappe.has_permission("Card Equipment", "read", other):
				frappe.throw(
					_("{0} {1} is already used by equipment {2} in company {3}.").format(
						label, self.get(field), other, self.company
					),
					title=_("Duplicate equipment"),
				)
			frappe.throw(
				_("{0} {1} is already used by another equipment in company {2}.").format(
					label, self.get(field), self.company
				),
				title=_("Duplicate equipment"),
			)

	def _refuse_unreadable_asset(self, asset):
		frappe.throw(
			_("You are not permitted to read Asset {0}, so you cannot link it.").format(asset),
			frappe.PermissionError,
		)

	def keep_derived_location(self):
		"""#56: current_project / assignment_date are written only by
		card.transfer.sync_equipment_location (db.set_value). read_only is a Desk
		property, so a save (REST and imports included) never sets them: a new
		equipment starts empty, an existing one keeps the stored values."""
		before = None if self.is_new() else self.get_doc_before_save()
		for fieldname in ("current_project", "assignment_date"):
			self.set(fieldname, before.get(fieldname) if before else None)

	def validate_company_change(self):
		"""#56: the equipment's company decides the company of its cards, postings
		and reports; once anything references the equipment it cannot move."""
		if not self._company_changed():
			return
		references = list(COMPANY_BOUND_REFERENCES)
		if frappe.get_meta("GL Entry").has_field("card_equipment"):
			references.append(("GL Entry", "card_equipment"))  # e.g. Asset depreciation
		for doctype, field in references:
			if frappe.db.exists(doctype, {field: self.name}):
				frappe.throw(
					_(
						"Equipment {0} is already used in {1}; its company cannot change. Create a new equipment record for the other company."
					).format(self.name, _(doctype))
				)

	def _company_changed(self):
		return not self.is_new() and self.has_value_changed("company")

	def validate_asset_link(self):
		"""#56: linking an Asset writes the equipment onto it as its accounting
		dimension (card.dimension.sync_asset_dimension), so the Asset must be of
		the equipment's company, not cancelled, and readable by the user."""
		asset = self.get(ASSET_LINK_FIELD)
		changed = self.is_new() or self.has_value_changed(ASSET_LINK_FIELD) or self._company_changed()
		if not asset or not changed:
			return
		values = frappe.db.get_value("Asset", asset, ["company", "docstatus"], as_dict=True)
		if not values:
			return  # frappe's link validation reports the missing Asset
		if not frappe.has_permission("Asset", "read", asset):
			self._refuse_unreadable_asset(asset)
		if values.docstatus == 2:
			frappe.throw(_("Asset {0} is cancelled and cannot be linked.").format(asset))
		if values.company != self.company:
			frappe.throw(
				_("Asset {0} belongs to company {1}; equipment {2} belongs to {3}.").format(
					asset, values.company, self.name or self.equipment_name, self.company
				)
			)

	def keep_derived_unit_component(self):
		"""WP-05: is_unit_component is derived from the units' component tables
		(sync_unit_component_flags), never written by a save (REST and imports included):
		a new equipment starts with the derived value, an existing one keeps the stored one."""
		if self.is_new():
			self.is_unit_component = 1 if self.name and unit_of_component(self.name) else 0
			return
		self.is_unit_component = cint(frappe.db.get_value(self.doctype, self.name, "is_unit_component"))

	def validate_owned_unit(self):
		"""#42 (WP-04): a combined unit and each of its pieces are owned equipment. Checked
		when a record becomes a unit or a piece, or its ownership changes, so a legacy rented
		unit is never blocked by an unrelated save (get_unit_integrity_issues lists it)."""
		if self.ownership == OWNED:
			return
		ownership = _(self.meta.get_label("ownership"))
		became_unit = self.is_unit and (self.is_new() or self.has_value_changed("is_unit"))
		if became_unit or (self.is_unit and self.has_value_changed("ownership")):
			frappe.throw(
				_("Only owned equipment can be a unit. Set {0} to owned or untick the unit option.").format(
					ownership
				),
				title=_("Unit needs owned equipment"),
			)
		if not self.is_new() and self.has_value_changed("ownership"):
			# locking read: a unit saved at the same moment that adds this piece is seen
			# (its save locks this equipment row and re-reads the ownership the same way)
			unit = unit_of_component(self.name, for_update=True)
			if unit:
				frappe.throw(
					_(
						"Equipment {0} is a component of unit {1}; a unit component must be owned. Take it out of the unit first."
					).format(self.name, unit),
					title=_("Unit needs owned equipment"),
				)

	def validate_components(self):
		"""#56: a unit's components decide which assignments its card days are
		checked against (card.transfer.validate_card_days)."""
		rows = self.get("components") or []
		before = self.get_doc_before_save()
		if before and not self.has_value_changed("is_unit") and not self._company_changed():
			if _component_keys(before.get("components") or []) == _component_keys(rows):
				return
		# WP-04: only a piece that joins the unit now is checked for ownership
		was_open = {
			r.component for r in (before.get("components") if before else None) or [] if not r.to_date
		}
		joining = {r.component for r in rows if r.component and not r.get("to_date")} - was_open
		check_unit_components(self.name, self.company, self.is_unit, rows, self.ownership, joining)

	def apply_new_record_defaults(self):
		# Card Settings pre-fill for NEW equipment only; a provided value is never overridden.
		if not self.is_new():
			return
		default_hours = flt(setting("default_daily_hours"))
		if not flt(self.daily_hours) and default_hours > 0:
			self.daily_hours = default_hours
		fuel_on = setting("default_fuel_charged_to")
		if not self.get("الوقود_على") and fuel_on:
			self.set("الوقود_على", fuel_on)
		operator_on = setting("default_operator_on")
		if not self.operator_on and operator_on:
			self.operator_on = operator_on
		# F.5: default calculation basis for both sides (new records only)
		basis = setting("default_rate_basis")
		if basis:
			if not self.rate_type:
				self.rate_type = basis
			if not self.customer_rate_type:
				self.customer_rate_type = basis


def _component_keys(rows):
	return [(r.get("component"), str(r.get("from_date") or ""), str(r.get("to_date") or "")) for r in rows]


def check_unit_components(unit, company, is_unit, rows, ownership=None, joining=()):
	"""#56: the component rules of a unit, shared by the unit's save
	(CardEquipment.validate_components) and a component row saved on its own
	(CardEquipmentComponent.validate).

	v3.0.0: a row with a `to_date` is history (the piece left the unit), so only rows
	still in the unit count for "listed twice" and "already belongs to another unit".

	#42 (WP-04): a piece that joins the unit (`joining`) must be owned, and so must the
	unit it joins. Pieces already in a legacy unit are not re-checked, so closing their
	rows (taking them out) stays possible."""
	if rows and not is_unit:
		frappe.throw(_("Only a unit can list components."))
	if joining and ownership != OWNED:
		frappe.throw(
			_(
				"Only owned equipment can be a unit; unit {0} is not owned, so no component can join it."
			).format(unit),
			title=_("Unit needs owned equipment"),
		)
	for row in rows:
		if row.get("from_date") and row.get("to_date") and getdate(row.to_date) < getdate(row.from_date):
			frappe.throw(_("Component {0}: the To date is before the From date.").format(row.component))
	components = [row.component for row in rows if not row.get("to_date")]
	if is_unit and unit:
		# for_update (#59): a locking read returns the latest committed membership,
		# not the transaction's snapshot (MariaDB default REPEATABLE READ).
		parent = frappe.db.get_value(
			"Card Equipment Component",
			{"parenttype": "Card Equipment", "component": unit},
			"parent",
			for_update=True,
		)
		if parent:
			frappe.throw(
				_("Equipment {0} is a component of unit {1}; a component cannot be a unit.").format(
					unit, parent
				)
			)
	seen = set()
	for component in components:
		if not component:
			continue
		if component == unit:
			frappe.throw(_("A unit cannot be its own component."))
		if component in seen:
			frappe.throw(_("Component {0} is listed twice.").format(component))
		seen.add(component)
		# for_update (#59): two transactions claiming the same component both lock
		# its equipment row here, so the second waits until the first commits. The
		# membership read below is a locking read too — a plain read would still see
		# the transaction's pre-lock snapshot under MariaDB's default REPEATABLE
		# READ and miss the freshly committed row. Rows are read in idx order; a
		# crossed lock order between two multi-component units can deadlock, which
		# the database resolves by aborting one of the saves.
		info = frappe.db.get_value(
			"Card Equipment", component, ["company", "is_unit", "ownership"], as_dict=True, for_update=True
		)
		if not info:
			continue  # frappe's link validation reports the missing equipment
		if info.is_unit:
			frappe.throw(_("Component {0} is itself a unit.").format(component))
		if component in joining and info.ownership != OWNED:
			frappe.throw(
				_("Component {0} is not owned equipment; only owned equipment can be part of a unit.").format(
					component
				),
				title=_("Unit needs owned equipment"),
			)
		if info.company != company:
			frappe.throw(
				_("Component {0} belongs to company {1}; the unit belongs to {2}.").format(
					component, info.company, company
				)
			)
		other = frappe.db.get_value(
			"Card Equipment Component",
			{
				"parenttype": "Card Equipment",
				"component": component,
				"parent": ["!=", unit or ""],
				"to_date": ["is", "not set"],
			},
			"parent",
			for_update=True,
		)
		if other:
			frappe.throw(_("Component {0} already belongs to unit {1}.").format(component, other))


# ---------- WP-05: the unit-component flag follows the units' component tables ----------
_COMPONENT_ROWS = {"parenttype": "Card Equipment", "parentfield": "components"}


def unit_of_component(equipment, for_update=False):
	"""The unit `equipment` is a current component of (a row with no To date), else None.
	for_update: a locking read, which returns the latest committed rows (MariaDB REPEATABLE
	READ), as check_unit_components does when a piece joins a unit."""
	if not equipment:
		return None
	return frappe.db.get_value(
		"Card Equipment Component",
		{**_COMPONENT_ROWS, "component": equipment, "to_date": ["is", "not set"]},
		"parent",
		for_update=for_update,
	)


def component_periods(equipment):
	"""Every period `equipment` was or is a component of a unit: [{unit, from_date, to_date}]
	(an empty date is open on that side)."""
	return frappe.get_all(
		"Card Equipment Component",
		filters={**_COMPONENT_ROWS, "component": equipment},
		fields=["parent as unit", "from_date", "to_date"],
	)


def derived_unit_component(equipment):
	return 1 if unit_of_component(equipment) else 0


def sync_unit_component_flags(pieces):
	"""Store the derived is_unit_component of each piece (db.set_value: the piece's own
	validate and on_update do not run, its modified date stays). A change leaves a comment
	on the piece."""
	for piece in sorted(p for p in pieces if p):
		stored = frappe.db.get_value("Card Equipment", piece, "is_unit_component")
		if stored is None:
			continue  # the piece no longer exists
		derived = derived_unit_component(piece)
		if cint(stored) == derived:
			continue
		frappe.db.set_value("Card Equipment", piece, "is_unit_component", derived, update_modified=False)
		unit = unit_of_component(piece)
		frappe.get_doc("Card Equipment", piece).add_comment(
			"Info",
			_("Unit component flag set from the component table of unit {0}.").format(unit)
			if derived
			else _("Unit component flag cleared: the equipment is no longer a current component of a unit."),
		)


def unit_integrity_issues(equipment_rows):
	"""#42/WP-04 and WP-05: what the owned-only and derived-flag rules find in existing
	records, for the given equipment ({name, company, ownership, is_unit, is_unit_component}).
	Read-only: nothing is changed here."""
	by_name = {e.name: e for e in equipment_rows}
	if not by_name:
		return []
	open_rows = frappe.get_all(
		"Card Equipment Component",
		filters={**_COMPONENT_ROWS, "to_date": ["is", "not set"]},
		fields=["parent", "component"],
	)
	listed = {
		r.component
		for r in frappe.get_all("Card Equipment Component", filters=_COMPONENT_ROWS, fields=["component"])
	}
	unit_of = {r.component: r.parent for r in open_rows if r.component}
	issues = []

	def add(issue, eq, unit=None):
		issues.append(
			frappe._dict(issue=issue, message=_(issue), equipment=eq.name, company=eq.company, unit=unit)
		)

	for eq in sorted(by_name.values(), key=lambda e: e.name):
		if cint(eq.is_unit) and eq.ownership != OWNED:
			add("Unit is not owned", eq)
		unit = unit_of.get(eq.name)
		if unit and eq.ownership != OWNED:
			add("Component is not owned", eq, unit)
		if cint(eq.is_unit_component) and not unit:
			# never listed in any unit: ambiguous (the unit's table may never have been filled in);
			# kept until a Card Manager resolves it (resync_unit_component_flag)
			add(
				"Component flag without a unit"
				if eq.name not in listed
				else "Component flag after leaving its unit",
				eq,
			)
		if unit and not cint(eq.is_unit_component):
			add("Current component without the flag", eq, unit)
	return issues


@frappe.whitelist(methods=["GET"])
def get_unit_integrity_issues(company: str | None = None):
	"""#42/WP-04, WP-05: existing records that break the owned-only unit rule or whose
	unit-component flag does not match the component tables, for the equipment the user may
	read (Company User Permissions apply). Read-only; nothing is changed."""
	frappe.has_permission("Card Equipment", "read", throw=True)
	filters = {"company": company} if company else {}
	rows = frappe.get_list(
		"Card Equipment",
		filters=filters,
		fields=["name", "company", "ownership", "is_unit", "is_unit_component"],
		limit_page_length=0,
	)
	return unit_integrity_issues(rows)


@frappe.whitelist(methods=["POST"])
def resync_unit_component_flag(equipment: str):
	"""WP-05: set one equipment's unit-component flag to the value its component rows give
	(for a flag the migration kept because it was ambiguous). Card Manager level: the flag
	is permission level 1, like the components table."""
	doc = frappe.get_doc("Card Equipment", equipment)
	doc.check_permission("write")
	if not doc.has_permlevel_access_to("is_unit_component", permission_type="write"):
		frappe.throw(
			_("You are not permitted to change the unit component flag of {0}.").format(equipment),
			frappe.PermissionError,
		)
	sync_unit_component_flags([equipment])
	return derived_unit_component(equipment)


def get_timeline_data(doctype: str, name: str) -> dict:
	"""Daily operating hours for the form-dashboard heatmap.

	Dispatched by frappe.desk.notifications.get_open_count via
	frappe.get_meta_module(doctype); mirrors hrms employee_master.get_timeline_data.
	Sums working_hours of submitted Card Monthly Card day rows per operation_date;
	dates with a zero total (stoppage days) are left out so their cells stay empty.
	"""
	frappe.has_permission(doctype, "read", name, throw=True)
	frappe.has_permission("Card Monthly Card", "read", throw=True)

	card = frappe.qb.DocType("Card Monthly Card")
	day = frappe.qb.DocType("Card Monthly Card Day")
	total_hours = Sum(day.working_hours)

	rows = (
		frappe.qb.from_(day)
		.join(card)
		.on(day.parent == card.name)
		.select(UnixTimestamp(day.operation_date), total_hours)
		.where((card.equipment == name) & (card.docstatus == 1))
		.groupby(day.operation_date)
		.having(total_hours > 0)
	).run()

	return {int(timestamp): flt(hours) for timestamp, hours in rows}


@frappe.whitelist()
def get_shift_heatmap(name: str):
	"""Per-shift daily operating hours, so two-shift equipment can show the day
	(نهاري) and night (ليلي) activity as two separate heatmaps with distinct
	palettes. Mirrors get_timeline_data but also groups by the card's shift.
	Returns {"day": {ts: hours}, "night": {ts: hours}, "has_night": bool}.
	"""
	frappe.has_permission("Card Equipment", "read", name, throw=True)
	frappe.has_permission("Card Monthly Card", "read", throw=True)

	card = frappe.qb.DocType("Card Monthly Card")
	day = frappe.qb.DocType("Card Monthly Card Day")
	total_hours = Sum(day.working_hours)

	rows = (
		frappe.qb.from_(day)
		.join(card)
		.on(day.parent == card.name)
		.select(UnixTimestamp(day.operation_date), card.shift, total_hours)
		.where((card.equipment == name) & (card.docstatus == 1))
		.groupby(day.operation_date, card.shift)
		.having(total_hours > 0)
	).run()

	day_map, night_map = {}, {}
	for timestamp, shift, hours in rows:
		(night_map if shift == "ليلي" else day_map)[int(timestamp)] = flt(hours)
	return {"day": day_map, "night": night_map, "has_night": bool(night_map)}


# ---------- v3.0.0: unit component changes (replace / move between units) ----------
# Owner decision 2026-10-18: a unit stays ONE equipment on its monthly card (billing
# unchanged); these actions only keep the dated history of the pieces inside it.


@frappe.whitelist(methods=["POST"])
def replace_component(unit: str, component: str, new_component: str, date: str, reason: str | None = None):
	"""From `date`, `new_component` takes the place of `component` in `unit`."""
	doc = frappe.get_doc("Card Equipment", unit)
	_check_components_write(doc)
	frappe.get_doc("Card Equipment", new_component).check_permission("read")
	day = getdate(date)
	row = _close_component(doc, component, day, reason)
	_check_component_on_project(doc, new_component, day)
	doc.append(
		"components",
		{"component": new_component, "role": row.role, "from_date": day, "change_reason": reason},
	)
	doc.save()
	return doc.name


@frappe.whitelist(methods=["POST"])
def move_component(unit: str, component: str, target_unit: str, date: str, reason: str | None = None):
	"""From `date`, `component` leaves `unit` and works in `target_unit` (same project)."""
	if unit == target_unit:
		frappe.throw(_("Choose another unit."))
	source = frappe.get_doc("Card Equipment", unit)
	_check_components_write(source)
	target = frappe.get_doc("Card Equipment", target_unit)
	_check_components_write(target)
	if not target.is_unit:
		frappe.throw(_("{0} is not a unit.").format(target_unit))
	day = getdate(date)
	row = _close_component(source, component, day, reason)
	_check_no_approved_card_from(target, day)
	_check_component_on_project(target, component, day)
	# close first: the target's "already belongs to another unit" check reads the DB.
	# The piece stays a component throughout: its flag is synced once, after both saves
	# (no cleared-then-set pair of comments)
	deferred = frappe.flags.get("card_defer_unit_flag_sync")
	frappe.flags.card_defer_unit_flag_sync = True
	try:
		source.save()
		target.append(
			"components",
			{"component": component, "role": row.role, "from_date": day, "change_reason": reason},
		)
		target.save()
	finally:
		frappe.flags.card_defer_unit_flag_sync = deferred
	sync_unit_component_flags(
		{r.component for doc in (source, target) for r in doc.components if r.component}
	)
	return target.name


def _check_components_write(unit_doc):
	"""`components` is permission level 1 (Card Manager writes, Card User reads): a level-0
	write is not enough, and frappe would silently drop the change on save."""
	unit_doc.check_permission("write")
	if not unit_doc.has_permlevel_access_to("components", permission_type="write"):
		frappe.throw(
			_("You are not permitted to change the components of {0}.").format(unit_doc.name),
			frappe.PermissionError,
		)


def _close_component(unit_doc, component, day, reason):
	if not unit_doc.is_unit:
		frappe.throw(_("{0} is not a unit.").format(unit_doc.name))
	row = next((r for r in unit_doc.components if r.component == component and not r.to_date), None)
	if not row:
		frappe.throw(_("{0} is not currently a component of {1}.").format(component, unit_doc.name))
	if row.from_date and day <= getdate(row.from_date):
		frappe.throw(_("The change date must be after {0}.").format(row.from_date))
	_check_no_approved_card_from(unit_doc, day)
	row.to_date = add_days(day, -1)
	row.change_reason = reason
	return row


def _check_no_approved_card_from(unit_doc, day):
	"""A change never rewrites an approved period: no submitted card of the unit may
	end on or after the change date."""
	card = frappe.db.get_value(
		"Card Monthly Card",
		{"equipment": unit_doc.name, "docstatus": 1, "to_date": [">=", day]},
		"name",
	)
	if card:
		frappe.throw(
			_(
				"Approved card {0} covers {1} or later; a unit change cannot apply to an approved period."
			).format(card, day)
		)


def _check_component_on_project(unit_doc, component, day):
	"""A piece works in a unit only while it is on the unit's project (moved there by an
	Equipment Transport). Equipment with no assignment history stays unconstrained."""
	from card.transfer import _assigned_on, _has_any_assignment

	project = unit_doc.current_project
	if project and _has_any_assignment(component) and not _assigned_on(component, project, day):
		frappe.throw(
			_("{0} is not on project {1} on {2}. Move it there with an Equipment Transport first.").format(
				component, project, day
			)
		)


def _differs(old, new):
	"""Compare stored vs incoming values without false positives from type
	(1 vs 1.0, None vs "", date vs "YYYY-MM-DD")."""
	if (old in (None, "")) and (new in (None, "")):
		return False
	if isinstance(old, (int, float)) or isinstance(new, (int, float)):
		return flt(old) != flt(new)
	return str(old) != str(new)
