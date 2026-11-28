"""Seed two fictitious customer Sales Invoices for the Desk-button screenshots (FR-194, FR-195).

Run by .github/workflows/docs-screenshots.yml after every other shot (it submits the cards below, which the
other shots must not see), on the disposable CI bench only. It submits the
October 2026 cards of the three customer-billing demo machines (CR-03, WL-05, MC-05) and books, by hand and with
fictitious data:

- "Card demo - unlinked invoice": Example Roads Co., project Valley Road Upgrade, net = the CR-03 card + the WL-05
  card. It stays unlinked, so the form shows "Link to monthly cards".
- "Card demo - linked invoice": Sample Infrastructure Ltd., project Industrial Park Phase 2, net = the MC-05 card.
  It is linked to that card with card.gl.integrity.link_customer_invoice, so the form shows "Remove link to
  monthly cards".

Re-running is safe: existing records are reused. It fails the job when a card or an invoice cannot be made.
"""

import frappe

COMPANY = "Example Contracting Co."
UNLINKED = "Card demo - unlinked invoice"
LINKED = "Card demo - linked invoice"
REASON = "Demo: the invoice was booked in ERPNext before the cards"


def _card(code):
	equipment = frappe.db.get_value("Card Equipment", {"equipment_name": ["like", f"%({code})%"]}, "name")
	name = frappe.db.get_value("Card Monthly Card", {"equipment": equipment, "month": "10"}, "name")
	if not name:
		raise RuntimeError(f"demo card of {code} is missing")
	doc = frappe.get_doc("Card Monthly Card", name)
	if doc.docstatus == 0:
		doc.submit()
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone CI script run outside a request
		doc.reload()
	if not (doc.docstatus == 1 and doc.customer and doc.customer_net_amount > 0):
		raise RuntimeError(f"demo card {name} ({code}) is not a submitted customer card with a net amount")
	return doc


def _invoice(remarks, customer, project, net):
	name = frappe.db.get_value("Sales Invoice", {"remarks": remarks}, "name")
	if name:
		return frappe.get_doc("Sales Invoice", name)
	from card.gl.masters import ensure_posting_masters, ensure_selling_price_list

	row = ensure_posting_masters(COMPANY)
	doc = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": COMPANY,
			"customer": customer,
			"set_posting_time": 1,
			"posting_date": "2026-10-31",
			"due_date": "2026-10-31",
			"currency": frappe.db.get_value("Company", COMPANY, "default_currency"),
			"selling_price_list": ensure_selling_price_list(COMPANY),
			"remarks": remarks,
			"items": [
				{
					"item_code": row.rental_out_item or row.rental_item,
					"qty": 1,
					"rate": net,
					"project": project,
					"income_account": row.equipment_rental_income_account,
					"cost_center": row.cost_center,
				}
			],
		}
	)
	doc.insert()
	doc.submit()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone CI script run outside a request
	print(f"+ Sales Invoice {doc.name} ({remarks})")
	return doc


def seed():
	from card.gl.integrity import link_customer_invoice

	valley = frappe.db.get_value("Project", {"project_name": "Valley Road Upgrade"}, "name")
	park = frappe.db.get_value("Project", {"project_name": "Industrial Park Phase 2"}, "name")
	crusher, loader, crane = _card("CR-03"), _card("WL-05"), _card("MC-05")
	_invoice(
		UNLINKED,
		"Example Roads Co.",
		valley,
		round(crusher.customer_net_amount + loader.customer_net_amount, 2),
	)
	linked = _invoice(LINKED, "Sample Infrastructure Ltd.", park, round(crane.customer_net_amount, 2))
	if not frappe.db.get_value("Card Monthly Card", crane.name, "sales_invoice"):
		link_customer_invoice(linked.name, [crane.name], REASON)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- standalone CI script run outside a request
	print("LINK_SEED_DONE")


seed()
