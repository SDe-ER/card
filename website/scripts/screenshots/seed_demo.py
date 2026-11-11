"""Seed a CARD demo site with fictitious data for the documentation screenshots.

Run on a disposable development site only (never on a production site):

    cd frappe-bench/sites
    ../env/bin/python -c "import frappe; frappe.init(site='demo.localhost', sites_path='.'); frappe.connect(); \
        frappe.set_user('Administrator'); exec(open('/path/to/seed_demo.py').read()); frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails"

The ERPNext setup wizard must have run first with the company "Example Contracting Co." (abbreviation EXC).
Every name, number and amount below is invented. Re-running the script is safe: existing records are reused.
"""

import frappe
from frappe.utils import add_days, getdate

COMPANY = "Example Contracting Co."
ABBR = "EXC"
YEAR, MONTH = 2026, 10
LOG = []


def log(msg):
	LOG.append(msg)
	print(msg)


def get_or_make(doctype, filters, values=None, submit=False):
	name = frappe.db.get_value(doctype, filters, "name")
	if name:
		return frappe.get_doc(doctype, name)
	doc = frappe.get_doc({"doctype": doctype, **filters, **(values or {})})
	try:
		doc.insert()
		if submit:
			doc.submit()
		log(f"+ {doctype} {doc.name}")
	except Exception as e:
		frappe.db.rollback()
		log(f"! {doctype} {filters}: {type(e).__name__}: {str(e)[:300]}")
		return None
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails
	return doc


def acc(name_part, root=None):
	f = {"company": COMPANY, "is_group": 0, "account_name": ["like", f"%{name_part}%"]}
	if root:
		f["root_type"] = root
	return frappe.db.get_value("Account", f, "name")


def seed():
	# ---------------------------------------------------------------- ERPNext masters
	for g in ("Equipment Rental", "Fuel"):
		get_or_make(
			"Supplier Group", {"supplier_group_name": g}, {"parent_supplier_group": "All Supplier Groups"}
		)

	SUPPLIERS = {
		"Desert Equipment Rentals": "Equipment Rental",
		"Northern Heavy Machinery": "Equipment Rental",
		"Coastal Fuel Supply": "Fuel",
	}
	for s, g in SUPPLIERS.items():
		get_or_make(
			"Supplier",
			{"supplier_name": s},
			{"supplier_group": g, "supplier_type": "Company", "country": "Saudi Arabia"},
		)

	for c in ("Example Roads Co.", "Sample Infrastructure Ltd."):
		get_or_make(
			"Customer",
			{"customer_name": c},
			{"customer_type": "Company", "customer_group": "Commercial", "territory": "All Territories"},
		)

	PROJECTS = {}
	for pname, cust in (
		("Valley Road Upgrade", "Example Roads Co."),
		("Industrial Park Phase 2", "Sample Infrastructure Ltd."),
		("North Bridge Works", "Example Roads Co."),
	):
		p = get_or_make(
			"Project",
			{"project_name": pname},
			{"company": COMPANY, "customer": cust, "status": "Open", "expected_start_date": "2026-09-01"},
		)
		if p:
			PROJECTS[pname] = p.name
			cc = get_or_make(
				"Cost Center",
				{"cost_center_name": pname, "company": COMPANY},
				{"parent_cost_center": f"{COMPANY} - {ABBR}", "is_group": 0},
			)
			if cc and not frappe.db.get_value("Project", p.name, "cost_center"):
				frappe.db.set_value("Project", p.name, "cost_center", cc.name)
				frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails

	EMPLOYEES = {}
	for first, last, gender in (
		("Ali", "Example", "Male"),
		("Omar", "Sample", "Male"),
		("Hassan", "Demo", "Male"),
		("Khalid", "Test", "Male"),
	):
		e = get_or_make(
			"Employee",
			{"first_name": first, "last_name": last},
			{
				"company": COMPANY,
				"gender": gender,
				"date_of_birth": "1990-01-15",
				"date_of_joining": "2025-01-01",
				"status": "Active",
			},
		)
		if e:
			EMPLOYEES[first] = e.name

	for uom in ("Litre", "Nos"):
		get_or_make("UOM", {"uom_name": uom})

	ITEMS = {
		"DIESEL": ("Diesel", "Litre", 1),
		"RENT-EQ": ("Equipment Rental", "Nos", 0),
		"TRANSPORT": ("Equipment Transport", "Nos", 0),
		"HF-100": ("Hydraulic Filter HF-100", "Nos", 1),
		"OIL-15W40": ("Engine Oil 15W-40", "Litre", 1),
		"BT-350": ("Bucket Tooth BT-350", "Nos", 1),
		"TW-500": ("Torque Wrench 500 Nm", "Nos", 1),
		"SAFETY-KIT": ("Operator Safety Kit", "Nos", 1),
	}
	for code, (iname, uom, stock) in ITEMS.items():
		get_or_make(
			"Item",
			{"item_code": code},
			{"item_name": iname, "item_group": "All Item Groups", "stock_uom": uom, "is_stock_item": stock},
		)

	for loc in ("Valley Road Site", "Industrial Park Site", "Main Workshop", "Central Yard"):
		get_or_make("Location", {"location_name": loc})

	store = frappe.db.get_value("Warehouse", {"company": COMPANY, "warehouse_name": "Stores"}, "name")
	custody = get_or_make(
		"Warehouse",
		{"warehouse_name": "Tool Custody", "company": COMPANY},
		{"parent_warehouse": f"All Warehouses - {ABBR}"},
	)
	cost_center = f"Main - {ABBR}"

	# stock for parts and tools
	if store and not frappe.db.exists("Stock Entry", {"remarks": "Demo opening stock", "docstatus": 1}):
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": COMPANY,
				"remarks": "Demo opening stock",
				"items": [
					{
						"item_code": c,
						"qty": q,
						"t_warehouse": store,
						"basic_rate": r,
						"cost_center": cost_center,
					}
					for c, q, r in (
						("HF-100", 12, 85),
						("OIL-15W40", 400, 9),
						("BT-350", 30, 140),
						("TW-500", 4, 650),
						("SAFETY-KIT", 10, 220),
					)
				],
			}
		)
		try:
			se.insert()
			se.submit()
			log(f"+ Stock Entry {se.name}")
		except Exception as e:
			frappe.db.rollback()
			log(f"! Stock Entry: {e}")

	# ---------------------------------------------------------------- CARD settings
	settings = frappe.get_single("Card Settings")
	if not any(r.company == COMPANY for r in settings.company_settings):
		settings.append(
			"company_settings",
			{
				"company": COMPANY,
				"equipment_rental_expense_account": acc("Miscellaneous Expenses", "Expense")
				or acc("Expense", "Expense"),
				"diesel_expense_account": acc("Miscellaneous Expenses", "Expense"),
				"transport_expense_account": acc("Freight", "Expense")
				or acc("Miscellaneous Expenses", "Expense"),
				"equipment_rental_income_account": acc("Service", "Income") or acc("Sales", "Income"),
				"payable_account": acc("Creditors", "Liability"),
				"receivable_account": acc("Debtors", "Asset"),
				"cost_center": cost_center,
				"rental_item": "RENT-EQ",
				"diesel_item": "DIESEL",
				"transport_item": "TRANSPORT",
				"rental_out_item": "RENT-EQ",
				"initial_location": "Central Yard",
				"store_warehouse": store,
				"custody_warehouse": custody.name if custody else None,
			},
		)
		try:
			settings.save()
			log("+ Card Settings company row")
		except Exception as e:
			frappe.db.rollback()
			log(f"! Card Settings: {e}")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails

	for kind, tname in (
		("إضافة", "Generator rental"),
		("إضافة", "Extra transport"),
		("خصم", "Breakdown deduction"),
		("خصم", "Fuel advance"),
	):
		settings = frappe.get_single("Card Settings")
		tf = next(
			(
				f.fieldname
				for f in settings.meta.fields
				if f.fieldtype == "Table" and f.options == "Card Adjustment Type"
			),
			None,
		)
		if tf and not any(r.type_name == tname for r in settings.get(tf)):
			settings.append(
				tf,
				{
					"company": COMPANY,
					"type_name": tname,
					"kind": kind,
					"account": acc("Service", "Income")
					if kind == "إضافة"
					else acc("Miscellaneous Expenses", "Expense"),
				},
			)
			try:
				settings.save()
				log(f"+ adjustment type {tname}")
			except Exception as e:
				frappe.db.rollback()
				log(f"! adjustment type {tname}: {e}")
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails

	for reason in (
		"Waiting for customer instructions",
		"Hydraulic leak",
		"Weather (sand storm)",
		"No diesel on site",
	):
		get_or_make("Card Stop Reason", {"company": COMPANY, "reason_name": reason})

	# categories, types, makes, models
	TYPES = {
		"Crushers": ["Mobile Crusher"],
		"Earthmoving": ["Excavator", "Wheel Loader"],
		"Lifting": ["Mobile Crane"],
		"Power": ["Generator"],
	}
	for cat, types in TYPES.items():
		get_or_make("Card Equipment Category", {"category_name": cat})
		for t in types:
			get_or_make("Card Equipment Type", {"equipment_type_name": t}, {"equipment_category": cat})

	MAKES = {}
	for mk in ("Komatsu", "Caterpillar", "Volvo", "Liebherr", "Metso"):
		m = get_or_make("Card Equipment Make", {"make_name": mk})
		if m:
			MAKES[mk] = m.name
	MODELS = {}
	for mk, model, t in (
		("Komatsu", "PC350", "Excavator"),
		("Caterpillar", "966M", "Wheel Loader"),
		("Volvo", "EC480", "Excavator"),
		("Liebherr", "LTM 1100", "Mobile Crane"),
		("Metso", "LT120", "Mobile Crusher"),
		("Caterpillar", "C18 500 kVA", "Generator"),
	):
		if mk in MAKES:
			m = get_or_make(
				"Card Equipment Model",
				{"model_name": model, "equipment_make": MAKES[mk]},
				{"equipment_type": t},
			)
			if m:
				MODELS[model] = m.name

	# ---------------------------------------------------------------- equipment
	EQUIP = {}
	EQ_DEF = [
		# name, type, make, model, ownership, direction, extra
		(
			"Excavator PC350 (EX-01)",
			"Excavator",
			"Komatsu",
			"PC350",
			"ملك",
			"تشغيل داخلي",
			{
				"plate_no": "EX-1001",
				"serial_no": "KMT-PC350-0001",
				"internal_rate_basis": "بالساعة",
				"internal_hourly_rate": 150,
				"meter_type": "ساعات",
				"opening_meter": 4200,
				"current_meter": 4630,
				"tank_capacity": 600,
				"service_interval_hours": 250,
				"last_service_meter": 4500,
			},
		),
		(
			"Wheel Loader 966M (WL-02)",
			"Wheel Loader",
			"Caterpillar",
			"966M",
			"إيجار",
			"مستأجَرة من مورد",
			{
				"supplier": "Desert Equipment Rentals",
				"rate_type": "باليوم",
				"rate": 1200,
				"operator_on": "المؤجر",
				"الوقود_على": "الشركة",
				"rental_start_date": "2026-09-01",
				"contract_no": "DER-2026-014",
				"plate_no": "WL-2002",
				"meter_type": "ساعات",
			},
		),
		(
			"Mobile Crusher LT120 (CR-03)",
			"Mobile Crusher",
			"Metso",
			"LT120",
			"ملك",
			"مؤجَّرة لعميل",
			{
				"customer_rate_type": "باليوم",
				"customer_rate": 2500,
				"default_customer": "Example Roads Co.",
				"day_billing_basis": "Full day",
				"serial_no": "MTS-LT120-0003",
				"meter_type": "ساعات",
			},
		),
		(
			"Generator 500 kVA (GN-04)",
			"Generator",
			"Caterpillar",
			"C18 500 kVA",
			"ملك",
			"تشغيل داخلي",
			{
				"serial_no": "CAT-C18-0004",
				"internal_rate_basis": "باليوم",
				"internal_rate": 500,
				"meter_type": "ساعات",
			},
		),
		(
			"Mobile Crane LTM 1100 (MC-05)",
			"Mobile Crane",
			"Liebherr",
			"LTM 1100",
			"إيجار",
			"إيجار من الباطن",
			{
				"supplier": "Northern Heavy Machinery",
				"rate_type": "بالساعة",
				"rate": 320,
				"customer_rate_type": "بالساعة",
				"customer_rate": 390,
				"default_customer": "Sample Infrastructure Ltd.",
				"operator_on": "المؤجر",
				"الوقود_على": "المؤجر",
				"plate_no": "MC-5005",
			},
		),
		(
			"Excavator EC480 (EX-06)",
			"Excavator",
			"Volvo",
			"EC480",
			"إيجار",
			"مستأجَرة من مورد",
			{
				"supplier": "Northern Heavy Machinery",
				"rate_type": "بالساعة",
				"rate": 180,
				"operator_on": "الشركة",
				"الوقود_على": "الشركة",
				"plate_no": "EX-6006",
				"meter_type": "ساعات",
			},
		),
	]
	for name, typ, mk, model, own, direction, extra in EQ_DEF:
		vals = {
			"company": COMPANY,
			"ownership": own,
			"rental_direction": direction,
			"equipment_type": typ,
			"equipment_make": MAKES.get(mk),
			"equipment_model": MODELS.get(model),
			"manufacture_year": 2021,
			"daily_hours": 10,
			"status": "نشطة",
		}
		vals.update(extra)
		e = get_or_make("Card Equipment", {"equipment_name": name}, vals)
		if e:
			EQUIP[name.split("(")[1].rstrip(")")] = e.name

	# assignments
	for code, proj, start in (
		("EX-01", "Valley Road Upgrade", "2026-09-05"),
		("WL-02", "Valley Road Upgrade", "2026-09-05"),
		("CR-03", "Valley Road Upgrade", "2026-09-17"),
		("GN-04", "Valley Road Upgrade", "2026-09-17"),
		("MC-05", "Industrial Park Phase 2", "2026-09-10"),
		("EX-06", "Industrial Park Phase 2", "2026-09-10"),
	):
		if code in EQUIP and proj in PROJECTS:
			get_or_make(
				"Card Equipment Assignment",
				{"equipment": EQUIP[code], "project": PROJECTS[proj]},
				{
					"from_date": start,
					"site_location": "Valley Road Site" if "Valley" in proj else "Industrial Park Site",
					"cost_center": cost_center,
				},
			)
			a = frappe.db.get_value(
				"Card Equipment Assignment", {"equipment": EQUIP[code], "project": PROJECTS[proj]}, "name"
			)
			if a and not frappe.db.get_value("Card Equipment Assignment", a, "from_date"):
				frappe.db.set_value("Card Equipment Assignment", a, "from_date", start)

	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails
	log("SEED_PART1_DONE")

	# ---------------------------------------------------------------- monthly cards (October 2026)
	STOP = frappe.get_all("Card Stop Reason", filters={"company": COMPANY}, pluck="name", order_by="creation")

	def month_days(pattern):
		"""pattern: callable(day) -> (status, hours, stop_reason_index or None, stopped_hours, note)."""
		rows = []
		for d in range(1, 32):
			date = getdate(f"{YEAR}-{MONTH:02d}-{d:02d}")
			status, hours, sr, sh, note = pattern(d, date)
			row = {"operation_date": date, "day_status": status, "working_hours": hours, "notes": note}
			if sr is not None and STOP:
				row.update(
					{
						"stop_reason": STOP[sr],
						"stopped_hours": sh,
						"responsible_party_type": "Customer" if sr == 0 else "Company",
					}
				)
			rows.append(row)
		return rows

	def normal(d, date):
		if date.weekday() == 4:  # Friday
			return ("إجازة", 0, None, 0, "Weekly rest day")
		if d == 14:
			return ("عطل", 4, 1, 6, "Hydraulic hose replaced on site")
		if d == 22:
			return ("توقف من العميل", 0, 0, 10, "Customer suspended work for inspection")
		return ("عمل", 10, None, 0, "")

	def crusher(d, date):
		if d < 21:
			return ("توقف من العميل", 0, 0, 10, "Waiting for customer to release the site")
		if date.weekday() == 4:
			return ("إجازة", 0, None, 0, "Weekly rest day")
		return ("عمل", 10, None, 0, "")

	CARDS = {}
	for code, proj, pattern, extra in (
		("EX-01", "Valley Road Upgrade", normal, {}),
		("WL-02", "Valley Road Upgrade", normal, {}),
		(
			"CR-03",
			"Valley Road Upgrade",
			crusher,
			{
				"adjustments": [
					{
						"adjustment_type": "إضافة",
						"description": "Generator rental 17-09-2026 to 20-10-2026 (34 days x SAR 500)",
						"amount": 17000,
						"side": "Customer",
					}
				]
			},
		),
		("MC-05", "Industrial Park Phase 2", normal, {}),
		("EX-06", "Industrial Park Phase 2", normal, {}),
	):
		if code not in EQUIP or proj not in PROJECTS:
			continue
		vals = {"company": COMPANY, "year": YEAR, "days": month_days(pattern)}
		vals.update(extra)
		c = get_or_make(
			"Card Monthly Card",
			{"equipment": EQUIP[code], "project": PROJECTS[proj], "month": f"{MONTH:02d}", "shift": "نهاري"},
			vals,
		)
		if c:
			CARDS[code] = c.name

	# submit two cards so the submitted view, statements and posting have data
	for code in ("WL-02", "EX-06"):
		n = CARDS.get(code)
		if n and frappe.db.get_value("Card Monthly Card", n, "docstatus") == 0:
			try:
				frappe.get_doc("Card Monthly Card", n).submit()
				log(f"+ submitted {n}")
			except Exception as e:
				frappe.db.rollback()
				log(f"! submit {n}: {str(e)[:300]}")
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails

	# ---------------------------------------------------------------- daily log
	if "Valley Road Upgrade" in PROJECTS:
		rows = [
			{"equipment": EQUIP["EX-01"], "day_hours": 10, "night_hours": 0},
			{
				"equipment": EQUIP["WL-02"],
				"day_hours": 8,
				"night_hours": 0,
				"stop_reason": STOP[1] if STOP else None,
				"stopped_hours": 2,
				"responsible_party_type": "Company",
				"notes": "Hose change",
			},
			{"equipment": EQUIP["CR-03"], "day_hours": 10, "night_hours": 4},
			{"equipment": EQUIP["GN-04"], "day_hours": 12, "night_hours": 8},
		]
		get_or_make(
			"Card Daily Log",
			{"company": COMPANY, "project": PROJECTS["Valley Road Upgrade"], "log_date": "2026-11-02"},
			{"rows": rows, "notes": "Dust control on the haul road during the afternoon."},
		)

	# ---------------------------------------------------------------- transport
	if "North Bridge Works" in PROJECTS:
		get_or_make(
			"Equipment Transport",
			{
				"company": COMPANY,
				"date": "2026-11-05",
				"remarks": "Demo: excavator and generator moved to the bridge site",
			},
			{
				"destination_type": "Project",
				"project": PROJECTS["North Bridge Works"],
				"transport_supplier": "Northern Heavy Machinery",
				"transport_method": "Low-bed",
				"from_location": "Valley Road Site",
				"to_location": "North Bridge Site",
				"responsibility": "Company bears the cost",
				"cost_basis": "Project",
				"cost_project": PROJECTS["North Bridge Works"],
				"amount": 4200,
				"items": [{"card_equipment": EQUIP["EX-01"]}, {"card_equipment": EQUIP["GN-04"]}],
			},
		)

	# ---------------------------------------------------------------- diesel
	settings = frappe.get_single("Card Settings")
	if not any(r.company == COMPANY for r in settings.diesel_price_schedule):
		settings.append(
			"diesel_price_schedule",
			{
				"company": COMPANY,
				"valid_from": "2026-01-01",
				"unit_price": 1.66,
				"currency": "SAR",
				"uom": "Litre",
			},
		)
		try:
			settings.save()
			log("+ diesel price")
		except Exception as e:
			frappe.db.rollback()
			log(f"! diesel price: {e}")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails
	if "Valley Road Upgrade" in PROJECTS:
		get_or_make(
			"Project Diesel Fill",
			{"company": COMPANY, "date": "2026-10-12", "project": PROJECTS["Valley Road Upgrade"]},
			{
				"supplier": "Coastal Fuel Supply",
				"opening_reading": 18240,
				"closing_reading": 19140,
				"litres": 900,
				"equipment_filled": [
					{"card_equipment": EQUIP["EX-01"]},
					{"card_equipment": EQUIP["WL-02"]},
					{"card_equipment": EQUIP["GN-04"]},
				],
			},
		)

	# ---------------------------------------------------------------- meter readings
	for dt, hours in (
		("2026-10-04 07:00:00", 4410),
		("2026-10-11 07:00:00", 4470),
		("2026-10-18 07:00:00", 4530),
		("2026-10-25 07:00:00", 4590),
	):
		get_or_make(
			"Equipment Meter Reading",
			{"equipment": EQUIP["EX-01"], "reading_datetime": dt},
			{"company": COMPANY, "engine_hours": hours, "source": "Weekly reading"},
			submit=True,
		)

	# ---------------------------------------------------------------- rate agreement
	get_or_make(
		"Card Rate Agreement",
		{"company": COMPANY, "supplier": "Desert Equipment Rentals", "equipment_type": "Wheel Loader"},
		{
			"valid_from": "2026-09-01",
			"valid_to": "2027-08-31",
			"currency": "SAR",
			"daily_rate": 1200,
			"hourly_rate": 130,
			"remarks": "Demo agreement: operator by the supplier, fuel by the company.",
		},
	)

	# ---------------------------------------------------------------- needs request
	if EMPLOYEES:
		frappe.db.set_value("Card Equipment", EQUIP["EX-01"], "operator", EMPLOYEES.get("Ali"))
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails
		get_or_make(
			"Equipment Needs Request",
			{"equipment": EQUIP["EX-01"], "request_date": "2026-11-03"},
			{
				"company": COMPANY,
				"project": PROJECTS.get("Valley Road Upgrade"),
				"operator": EMPLOYEES.get("Ali"),
				"items": [
					{
						"kind": "Part",
						"item_code": "HF-100",
						"qty": 2,
						"uom": "Nos",
						"reason": "Scheduled 250 h service",
					},
					{
						"kind": "Part",
						"item_code": "OIL-15W40",
						"qty": 40,
						"uom": "Litre",
						"reason": "Scheduled 250 h service",
					},
					{"kind": "Tool", "item_code": "TW-500", "qty": 1, "uom": "Nos", "reason": "Track bolts"},
				],
				"notes": "Service due within the week.",
			},
		)

	# ---------------------------------------------------------------- tool custody
	if EMPLOYEES and store:
		get_or_make(
			"Employee Tool Custody",
			{"employee": EMPLOYEES.get("Omar"), "item_code": "SAFETY-KIT", "date": "2026-10-05"},
			{
				"company": COMPANY,
				"movement": "Handover",
				"qty": 1,
				"warehouse": store,
				"project": PROJECTS.get("Valley Road Upgrade"),
				"card_equipment": EQUIP.get("WL-02"),
				"notes": "Issued at site induction.",
			},
		)

	# ---------------------------------------------------------------- parts fitment
	for item, model, status in (
		("HF-100", "PC350", "Pending Technical Review"),
		("BT-350", "PC350", "Pending Technical Review"),
		("HF-100", "EC480", "Pending Technical Review"),
	):
		if model in MODELS:
			get_or_make(
				"Card Equipment Part",
				{"item_code": item, "applies_to": "Equipment Model", "equipment_model": MODELS[model]},
				{
					"compatibility_status": status,
					"evidence_source": "Maker parts book",
					"evidence_reference": "Parts book section 7, page 42 (demo)",
				},
			)

	# ---------------------------------------------------------------- demo operator (CARD Mobile and the needs page)
	if not frappe.db.exists("User", "operator@example.com"):
		u = frappe.get_doc(
			{
				"doctype": "User",
				"email": "operator@example.com",
				"first_name": "Ali",
				"last_name": "Example",
				"send_welcome_email": 0,
				"new_password": "Demo-Pass-2026",
			}
		)
		u.append("roles", {"role": "Card Operator"})
		u.insert()
		log("+ User operator@example.com")
	if EMPLOYEES.get("Ali"):
		frappe.db.set_value("Employee", EMPLOYEES["Ali"], "user_id", "operator@example.com")

	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone seeding script run outside a request; each record is kept even if a later one fails
	log("SEED_DONE")


seed()
