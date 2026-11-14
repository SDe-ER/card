"""Prepare a throwaway CI bench site for the documentation screenshots.

Run by .github/workflows/docs-screenshots.yml inside the CI bench (test_site) before seed_demo.py. It replaces the
ERPNext setup wizard with the minimum the demo data needs: the company, a fiscal year, a demo manager user and a login
for capture.mjs. Everything created is fictitious and lives only on the CI runner.

Environment:
  DEMO_PASS       password of the demo manager user (generated per run by the workflow, masked in the log)
"""

import os

import frappe
from frappe.utils import getdate

COMPANY = "Example Contracting Co."
ABBR = "EXC"
MANAGER = "demo.manager@example.com"


def ensure_warehouse_types():
	# The setup wizard creates these; the company insert and CARD's diesel tanks need them.
	for name in ("Transit", "Fuel Tank"):
		if not frappe.db.exists("Warehouse Type", name):
			frappe.get_doc({"doctype": "Warehouse Type", "name": name}).insert(ignore_permissions=True)


def ensure_company():
	if frappe.db.exists("Company", COMPANY):
		return
	frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": COMPANY,
			"abbr": ABBR,
			"default_currency": "SAR",
			"country": "Saudi Arabia",
			"create_chart_of_accounts_based_on": "Standard Template",
			"chart_of_accounts": "Standard",
		}
	).insert(ignore_permissions=True)


def ensure_fiscal_year():
	if frappe.db.exists("Fiscal Year", "2026"):
		return
	frappe.get_doc(
		{
			"doctype": "Fiscal Year",
			"year": "2026",
			"year_start_date": getdate("2026-01-01"),
			"year_end_date": getdate("2026-12-31"),
			"companies": [{"company": COMPANY}],
		}
	).insert(ignore_permissions=True)


def ensure_manager(password):
	if not frappe.db.exists("User", MANAGER):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": MANAGER,
				"first_name": "Demo",
				"last_name": "Manager",
				"send_welcome_email": 0,
				"new_password": password,
				"language": "en",
			}
		)
		for role in ("System Manager", "Card Manager"):
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
	return frappe.get_doc("User", MANAGER)


def prepare():
	ensure_warehouse_types()
	ensure_company()
	ensure_fiscal_year()
	ensure_manager(os.environ["DEMO_PASS"])
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone CI bootstrap run outside a request
	print("BOOTSTRAP_DONE")


prepare()
