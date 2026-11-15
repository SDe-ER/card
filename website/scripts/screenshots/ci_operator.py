"""Configure the synthetic CARD operator for the mobile and needs screens, then check it the way CARD does.

Run by .github/workflows/docs-screenshots.yml after seed_demo.py. CARD decides that a user may ask for equipment
needs (card/materials.py: session_employee, portal_context, PORTAL_ROLES): an Active Employee whose user_id is the
user, and the user holds Card Operator (or a review role). This script sets exactly those, then prints CARD's own
answer for the operator (no secret is printed).
"""

import frappe

OPERATOR = "operator@example.com"
EMPLOYEE_NAME = ("Ali", "Example")


def _as_user(user):
	# nosemgrep: frappe-setuser -- standalone CI script, operator session check
	frappe.set_user(user)


def configure():
	if not frappe.db.exists("User", OPERATOR):
		print("OPERATOR_MISSING")
		return
	user = frappe.get_doc("User", OPERATOR)
	if "Card Operator" not in [r.role for r in user.roles]:
		user.append("roles", {"role": "Card Operator"})
		user.save(ignore_permissions=True)
	employee = frappe.db.get_value(
		"Employee", {"first_name": EMPLOYEE_NAME[0], "last_name": EMPLOYEE_NAME[1]}, "name"
	)
	if employee:
		frappe.db.set_value("Employee", employee, {"user_id": OPERATOR, "status": "Active"})
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone CI bootstrap run outside a request
	frappe.clear_cache()


def check():
	from card.materials import portal_context, session_employee

	_as_user(OPERATOR)
	try:
		context = portal_context()
		employee = bool(session_employee(OPERATOR))
		allowed = bool(context.get("allowed"))
	finally:
		_as_user("Administrator")
	if not (employee and allowed):
		raise RuntimeError("operator is not allowed by CARD: employee and allowed must be True")
	print("OPERATOR_CHECK passed")


configure()
check()
