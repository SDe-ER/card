"""Upgrade rehearsal (go-live P0 #119, Owner decision D2): synthetic data only.

Seeds a v1.0.1 site shaped like a site in use (3 rented machines of one company, 3 assignments,
5 monthly cards: 1 submitted, 2 cancelled and amended), snapshots it, and after the upgrade
compares the data. Run from the bench `sites` folder:

    ../env/bin/python upgrade_rehearsal.py <site> seed
    ../env/bin/python upgrade_rehearsal.py <site> snapshot <file>
    ../env/bin/python upgrade_rehearsal.py <site> compare <before> <after> upgrade|idempotent
    ../env/bin/python upgrade_rehearsal.py <site> smoke

`compare` and `smoke` exit 1 on a failure. `smoke` rolls back everything it writes."""

import json
import sys

import frappe

COMPANY = "Rehearsal Contracting Co"
CARD_DOCTYPES_V101 = (
	"Card Equipment",
	"Card Equipment Assignment",
	"Card Equipment Category",
	"Card Equipment Supplier",
	"Card Equipment Type",
	"Card Monthly Card",
	"Card Monthly Card Adjustment",
	"Card Monthly Card Day",
)
# documents CARD must never create by itself during an upgrade
LEDGER_DOCTYPES = (
	"GL Entry",
	"Payment Ledger Entry",
	"Stock Ledger Entry",
	"Purchase Invoice",
	"Sales Invoice",
	"Journal Entry",
	"Payment Entry",
	"Stock Entry",
	"Material Request",
)
# fields of a v1.0.1 record that an upgrade must keep exactly
KEPT = {
	"Card Equipment": (
		"company",
		"ownership",
		"supplier",
		"equipment_name",
		"equipment_type",
		"serial_no",
		"plate_no",
		"rate_type",
		"rate",
		"daily_hours",
		"docstatus",
	),
	"Card Equipment Assignment": ("equipment", "project", "from_date", "to_date", "cost_center"),
	"Card Monthly Card": (
		"equipment",
		"project",
		"company",
		"supplier",
		"month",
		"year",
		"shift",
		"docstatus",
		"amended_from",
		"rate",
		"total_working_hours",
		"amount",
		"total_additions",
		"total_deductions",
		"net_amount",
	),
	"Card Monthly Card Day": ("parent", "operation_date", "working_hours"),
	"Card Monthly Card Adjustment": ("parent", "adjustment_type", "amount"),
}
# metadata whose rows must not change between two migrates
META_COUNTS = (
	"Role",
	"Workspace",
	"Workspace Sidebar",
	"Desktop Icon",
	"Custom Field",
	"Property Setter",
	"DocPerm",
	"Custom DocPerm",
	"Report",
	"Print Format",
	"Page",
	"Patch Log",
)


def _first_option(doctype, field):
	options = frappe.get_meta(doctype).get_field(field).options or ""
	return next(o for o in options.split("\n") if o)


def _option(doctype, field, wanted):
	options = [o for o in (frappe.get_meta(doctype).get_field(field).options or "").split("\n") if o]
	assert wanted in options, (doctype, field, wanted, options)
	return wanted


def _insert(values):
	return frappe.get_doc(values).insert(ignore_permissions=True)


def seed():
	assert not frappe.db.exists("Company", COMPANY), "already seeded"
	for doctype, name, extra in (
		("Warehouse Type", "Transit", {"name": "Transit"}),
		("UOM", "Nos", {"uom_name": "Nos"}),
	):
		if not frappe.db.exists(doctype, name):
			_insert({"doctype": doctype, **extra})
	_insert(
		{
			"doctype": "Company",
			"company_name": COMPANY,
			"abbr": "RCC",
			"default_currency": "SAR",
			"country": "Saudi Arabia",
		}
	)
	if not frappe.db.exists("Fiscal Year", "2026"):
		_insert(
			{
				"doctype": "Fiscal Year",
				"year": "2026",
				"year_start_date": "2026-01-01",
				"year_end_date": "2026-12-31",
			}
		)
	cost_center = frappe.db.get_value("Company", COMPANY, "cost_center")
	project = _insert(
		{"doctype": "Project", "project_name": "Rehearsal Road Project", "company": COMPANY}
	).name
	group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name") or (
		_insert(
			{
				"doctype": "Supplier Group",
				"supplier_group_name": "Rehearsal Rental",
				"parent_supplier_group": "All Supplier Groups",
			}
		).name
	)
	suppliers = [
		_insert(
			{"doctype": "Supplier", "supplier_name": f"Rehearsal Rental {n}", "supplier_group": group}
		).name
		for n in ("A", "B")
	]
	category = _insert(
		{"doctype": "Card Equipment Category", "category_name": "Rehearsal heavy equipment"}
	).name
	types = [
		_insert(
			{"doctype": "Card Equipment Type", "equipment_type_name": label, "equipment_category": category}
		).name
		for label in ("Rehearsal loader 980", "Rehearsal dozer")
	]
	rented = _option("Card Equipment", "ownership", "إيجار")
	per_day = _option("Card Equipment", "rate_type", "باليوم")
	machines = []
	for label, etype, supplier, serial in (
		("Loader 980 (1)", types[0], suppliers[0], None),
		("Dozer D155A", types[1], suppliers[1], None),
		("Loader 980 (2)", types[0], suppliers[0], "258963"),
	):
		machines.append(
			_insert(
				{
					"doctype": "Card Equipment",
					"company": COMPANY,
					"ownership": rented,
					"supplier": supplier,
					"equipment_name": label,
					"equipment_type": etype,
					"serial_no": serial,
					"rate_type": per_day,
					"rate": 900,
					"daily_hours": 10,
					"rental_start_date": "2026-09-01",
					"current_project": project,
				}
			).name
		)
	for machine in machines:
		_insert(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": machine,
				"project": project,
				"from_date": "2026-09-01",
				"cost_center": cost_center,
			}
		)
	shift = _first_option("Card Monthly Card", "shift")

	def card(machine):
		return _insert(
			{
				"doctype": "Card Monthly Card",
				"equipment": machine,
				"project": project,
				"company": COMPANY,
				"shift": shift,
				"month": "09",
				"year": 2026,
				"days": [{"operation_date": f"2026-09-{d:02d}", "working_hours": 10} for d in range(1, 6)],
			}
		)

	for machine in machines[:2]:  # submitted, cancelled, amended and submitted again
		first = card(machine)
		first.submit()
		first.cancel()
		amended = frappe.copy_doc(first)
		amended.amended_from = first.name
		amended.insert(ignore_permissions=True)
		amended.submit()
	card(machines[2]).submit()
	frappe.db.commit()  # nosemgrep: rehearsal site, synthetic data
	print(json.dumps(_summary(), indent=1, default=str))


def _summary():
	return {
		doctype: frappe.db.count(doctype) for doctype in CARD_DOCTYPES_V101 if frappe.db.table_exists(doctype)
	} | {"cards": frappe.get_all("Card Monthly Card", fields=["name", "docstatus", "amended_from"])}


def snapshot(path):
	data = {"records": {}, "ledger": {}, "meta": {}, "card_role_users": [], "transports": None}
	for doctype in KEPT:
		data["records"][doctype] = (
			{
				row.name: {field: row.get(field) for field in KEPT[doctype]}
				for row in frappe.get_all(doctype, fields=["name", *KEPT[doctype]], order_by="name")
			}
			if doctype not in ("Card Monthly Card Day", "Card Monthly Card Adjustment")
			else sorted(
				[
					[str(row.get(field)) for field in KEPT[doctype]]
					for row in frappe.db.get_all(doctype, fields=list(KEPT[doctype]))
				]
			)
		)
	data["counts"] = {doctype: frappe.db.count(doctype) for doctype in CARD_DOCTYPES_V101}
	data["ledger"] = {doctype: frappe.db.count(doctype) for doctype in LEDGER_DOCTYPES}
	data["meta"] = {
		doctype: frappe.db.count(doctype) for doctype in META_COUNTS if frappe.db.table_exists(doctype)
	}
	data["card_role_users"] = sorted(
		frappe.db.sql("select parent, role from `tabHas Role` where parenttype='User' and role like 'Card%%'")
	)
	if frappe.db.table_exists("Equipment Transport"):
		data["transports"] = frappe.db.count("Equipment Transport")
	data["patches"] = sorted(
		r[0] for r in frappe.db.sql("select patch from `tabPatch Log` where patch like 'card.%%'")
	)
	data["identity_keys"] = (
		frappe.get_all("Card Equipment", fields=["name", "serial_no_key", "plate_no_key"], order_by="name")
		if frappe.get_meta("Card Equipment").has_field("serial_no_key")
		else None
	)
	with open(path, "w") as f:
		json.dump(data, f, indent=1, default=str, ensure_ascii=False, sort_keys=True)
	print(f"snapshot {path}: {data['counts']}")


def compare(before_path, after_path, mode):
	with open(before_path) as f:
		before = json.load(f)
	with open(after_path) as f:
		after = json.load(f)
	failures = []

	def check(ok, message):
		print(("PASS " if ok else "FAIL ") + message)
		if not ok:
			failures.append(message)

	for doctype, rows in before["records"].items():
		check(rows == after["records"].get(doctype), f"{doctype}: every record and kept field unchanged")
	check(before["counts"] == after["counts"], f"record counts unchanged {after['counts']}")
	check(
		before["ledger"] == after["ledger"],
		f"no ledger / accounting / stock document created {after['ledger']}",
	)
	check(before["card_role_users"] == after["card_role_users"], "no user gained or lost a Card role")
	if mode == "upgrade":
		check(after["transports"] == 0, f"no Equipment Transport invented (found {after['transports']})")
		keys = after["identity_keys"] or []
		check(
			len(keys) == len(before["records"]["Card Equipment"]),
			"identity key fields present on every machine",
		)
		with_serial = [row for row in keys if row["serial_no_key"]]
		check(
			len(with_serial) == 1 and with_serial[0]["serial_no_key"] == "258963",
			"chassis number key backfilled",
		)
		missing = sorted(set(_patch_list()) - set(after["patches"]))
		check(not missing, f"every CARD patch ran once ({len(after['patches'])}); missing {missing}")
	else:
		check(before == after, "second migrate changed nothing (records, metadata counts, patches, keys)")
	print(json.dumps({"failures": failures}))
	sys.exit(1 if failures else 0)


def _patch_list():
	from frappe.modules.patch_handler import get_patches_from_app

	return [p for p in get_patches_from_app("card") if p.startswith("card.")]


def smoke():
	"""The upgraded legacy data stays usable (all rolled back): every legacy machine saves
	unchanged, a submitted card reloads, and a first transport can be recorded."""
	failures = []
	try:
		for name in frappe.get_all("Card Equipment", pluck="name"):
			try:
				frappe.get_doc("Card Equipment", name).save(ignore_permissions=True)
				print(f"PASS legacy equipment {name} saves unchanged")
			except Exception as e:
				failures.append(f"legacy equipment {name}: {e}")
		for name in frappe.get_all("Card Monthly Card", filters={"docstatus": 1}, pluck="name"):
			doc = frappe.get_doc("Card Monthly Card", name)
			doc.run_method("onload")
			print(f"PASS submitted card {name} loads ({doc.net_amount})")
		machine = frappe.get_all(
			"Card Equipment", filters={"company": COMPANY}, pluck="name", order_by="name"
		)[0]
		project = (
			frappe.get_doc(
				{"doctype": "Project", "project_name": "Rehearsal Second Project", "company": COMPANY}
			)
			.insert(ignore_permissions=True)
			.name
		)  # the machine moves to another project
		supplier = frappe.db.get_value("Supplier", {"supplier_name": "Rehearsal Rental A"}, "name")
		try:
			transport = frappe.get_doc(
				{
					"doctype": "Equipment Transport",
					"company": COMPANY,
					"equipment": machine,
					"project": project,
					"date": "2026-10-01",
					"transport_supplier": supplier,
					"amount": 500,
				}
			).insert(ignore_permissions=True)
			transport.submit()
			print(f"PASS first transport {transport.name} for legacy machine {machine} submitted")
		except Exception as e:
			failures.append(f"first transport for {machine}: {e}")
	finally:
		frappe.db.rollback()
	for failure in failures:
		print("FAIL " + failure)
	sys.exit(1 if failures else 0)


if __name__ == "__main__":
	site, command, *args = sys.argv[1:]
	frappe.init(site=site, sites_path=".")
	frappe.connect()
	try:
		{"seed": seed, "snapshot": snapshot, "compare": compare, "smoke": smoke}[command](*args)
	finally:
		frappe.destroy()
