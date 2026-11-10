# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-118 (#45, WP-09): seed the stop-reason catalogue of every company that has cards.

One Card Stop Reason per fixed non-working day status (إجازة, عطل, توقف من العميل), named
after the status, with billable OFF: today those statuses earn no rental (the card zeroes
their hours), so the seeded reasons bill exactly what the statuses bill. "عمل" is a working
status, not a stop reason, so it gets none.

Nothing else is written: no day row, no card, no status value changes. A reason is created
only when the company has none for that status yet (matched on its "Matching day status",
so a renamed or edited seeded reason is never re-created or reset) and none of the same
name exists. A second run writes nothing."""

import frappe

from card.card.doctype.card_stop_reason.card_stop_reason import reason_docname

SEED = (
	# (day status, default responsible party type)
	("إجازة", ""),
	("عطل", ""),
	("توقف من العميل", "Customer"),
)


def execute():
	if not frappe.db.table_exists("Card Stop Reason"):
		return
	companies = sorted(
		{
			c
			for c in frappe.get_all("Card Monthly Card", filters={"company": ["is", "set"]}, pluck="company")
			if c and frappe.db.exists("Company", c)
		}
	)
	for company in companies:
		for status, party_type in SEED:
			if frappe.db.exists("Card Stop Reason", {"company": company, "day_status": status}):
				continue
			if frappe.db.exists("Card Stop Reason", reason_docname(status, company)):
				continue
			frappe.get_doc(
				{
					"doctype": "Card Stop Reason",
					"company": company,
					"reason_name": status,
					"enabled": 1,
					"billable": 0,
					"day_status": status,
					"default_responsible_party_type": party_type,
				}
			).insert()
