import frappe
from frappe import _

from card.dimension import DIMENSION_FIELD, gl_has_dimension_field

# The CARD-mapped expense account fields on Card Company Settings (owner O3
# amendment 4: the account list comes from settings, never hardcoded).
EXPENSE_ACCOUNT_FIELDS = (
	"equipment_rental_expense_account",
	"diesel_expense_account",
	"transport_expense_account",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Report: "Equipment Expenses Without Equipment" (O3 guard report). Read-only.
	# Lists GL expense lines booked on the CARD-mapped expense accounts WITHOUT the
	# Card Equipment accounting dimension — every such line is a cost the per-equipment
	# P&L cannot see yet. First-run safe: without the dimension or the account settings
	# it returns a translated message, never a traceback.

	flt = frappe.utils.flt

	columns = [
		{"fieldname": "posting_date", "label": _("Posting date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 220,
		},
		{"fieldname": "voucher_type", "label": _("Voucher type"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160,
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 110,
		},
		{
			"fieldname": "cost_center",
			"label": _("Cost center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 130,
		},
		{"fieldname": "debit", "label": _("Debit"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "credit", "label": _("Credit"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 260},
	]

	if not gl_has_dimension_field():
		return [
			columns,
			[],
			_("The Card Equipment accounting dimension is not set up on this site yet."),
			None,
			[],
			True,
		]

	company = filters.get("company") or frappe.defaults.get_global_default("company")
	if not company:
		frappe.throw(_("Select a company"))

	row = frappe.db.get_value(
		"Card Company Settings",
		{"company": company},
		list(EXPENSE_ACCOUNT_FIELDS),
		as_dict=True,
	)
	if not row:
		return [columns, [], _("Configure Card Settings for company {0}").format(company), None, [], True]
	accounts = [row.get(f) for f in EXPENSE_ACCOUNT_FIELDS if row.get(f)]
	if not accounts:
		return [
			columns,
			[],
			_("Set the CARD expense accounts in Card Settings for company {0} first.").format(company),
			None,
			[],
			True,
		]

	glf = [
		["company", "=", company],
		["is_cancelled", "=", 0],
		["account", "in", accounts],
		[DIMENSION_FIELD, "is", "not set"],
	]
	if filters.get("from_date"):
		glf.append(["posting_date", ">=", filters.get("from_date")])
	if filters.get("to_date"):
		glf.append(["posting_date", "<=", filters.get("to_date")])

	rows = frappe.get_all(
		"GL Entry",
		filters=glf,
		fields=[
			"posting_date",
			"account",
			"voucher_type",
			"voucher_no",
			"project",
			"cost_center",
			"debit",
			"credit",
			"remarks",
		],
		order_by="posting_date asc, account asc",
		limit_page_length=0,
	)

	total = 0.0
	for r in rows:
		total = total + flt(r.debit) - flt(r.credit)

	summary = [
		{"label": _("Lines without equipment"), "value": len(rows), "datatype": "Int", "indicator": "Blue"},
		{
			"label": _("Net amount without equipment"),
			"value": flt(total, 2),
			"datatype": "Currency",
			"indicator": "Green" if not rows else "Red",
		},
	]
	message = _(
		"Expense lines on the CARD expense accounts with no Card Equipment dimension. "
		"Fix them at the source document so the per-equipment P&L stays complete."
	)
	return [columns, rows, message, None, summary, True]
