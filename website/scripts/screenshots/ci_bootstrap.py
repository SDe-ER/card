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


def install_base_masters():
	"""The ERPNext fixture installer the setup wizard runs (erpnext/setup/setup_wizard/setup_wizard.py L74-75,
	stage_fixtures -> fixtures.install(country)). It creates Item Group, Territory, Customer Group, Supplier Group,
	UOMs and the other base masters (erpnext/setup/setup_wizard/operations/install_fixtures.py L325-361)."""
	from erpnext.setup.setup_wizard.operations import install_fixtures

	install_fixtures.install("Saudi Arabia")
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone CI bootstrap run outside a request


def ensure_gender():
	# Not created by the installer above (not found in install_fixtures.py); the Employee link needs it.
	for name in ("Male", "Female"):
		if not frappe.db.exists("Gender", name):
			frappe.get_doc({"doctype": "Gender", "gender": name}).insert(ignore_permissions=True)


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
		# Accounts Manager: the monthly posting screen lists only the suppliers and customers the user can read
		# (card/gl/posting.py, month_parties), and System Manager and Card Manager read neither.
		# Accounts User: Asset Mapping Review and Equipment Meter Reconciliation need a role that reads Asset
		# (card/report_access.py, _role_reads), and ERPNext version-16 gives that read to Accounts User and
		# Quality Manager only (erpnext/assets/doctype/asset/asset.json), not to the three roles above.
		for role in ("System Manager", "Card Manager", "Accounts Manager", "Accounts User"):
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
	return frappe.get_doc("User", MANAGER)


def complete_setup():
	"""Complete the setup wizard the official way, so Desk opens on the workspace and not on the welcome screen.

	frappe v16 source (frappe/__init__.py, is_setup_complete): setup is complete when every 'Installed Application'
	row of frappe and erpnext has is_setup_complete = 1. enable_setup_wizard_complete(app) sets that flag for one app
	(frappe/desk/page/setup_wizard/setup_wizard.py, def enable_setup_wizard_complete). disable_future_access() in the
	same module sets System Settings.setup_complete from is_setup_complete(). Onboarding is switched off for the demo.
	"""
	from frappe.desk.page.setup_wizard.setup_wizard import enable_setup_wizard_complete

	for app in frappe.get_installed_apps():
		if frappe.db.exists("Installed Application", {"app_name": app}):
			enable_setup_wizard_complete(app)
	# disable_future_access() (setup_wizard.py L409-410) sets this default; without it Desk opens the welcome page.
	frappe.db.set_default("desktop:home_page", "workspace")
	frappe.db.set_single_value("System Settings", "enable_onboarding", 0)
	frappe.db.set_single_value("System Settings", "setup_complete", 1)
	use_classic_charts()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone CI bootstrap run outside a request
	frappe.clear_cache()
	frappe.clear_cache(doctype="System Settings")
	print("SETUP_COMPLETE", frappe.is_setup_complete())


def use_classic_charts():
	"""Draw charts and number cards the classic way, as a site updated from an earlier version does.

	A new site draws them as frappe-ui islands (System Settings.use_classic_charts = 0, frappe version-16
	frappe/public/js/frappe/ui/chart.js, is_classic). An island keeps its content in a shadow root, so capture.mjs
	cannot read the value of a number card, and in run 45656288398 every Arabic page with a chart was a plain white
	image. The field and its default are set the way frappe's own test does (test_system_settings.py,
	TestClassicChartsOnUpgrade). A frappe version without the field is left as it is.
	"""
	if not frappe.get_meta("System Settings").has_field("use_classic_charts"):
		return
	frappe.db.set_single_value("System Settings", "use_classic_charts", 1)
	frappe.db.set_default("use_classic_charts", 1)


def prepare():
	install_base_masters()
	ensure_gender()
	ensure_warehouse_types()
	ensure_company()
	ensure_fiscal_year()
	ensure_manager(os.environ["DEMO_PASS"])
	complete_setup()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone CI bootstrap run outside a request
	print("BOOTSTRAP_DONE")


prepare()
