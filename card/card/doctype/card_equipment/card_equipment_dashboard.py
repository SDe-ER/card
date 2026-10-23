# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe import _


def get_data():
	return {
		"heatmap": True,
		"heatmap_message": _("Daily operating hours from the monthly operation cards"),
		"fieldname": "equipment",
		# Project Diesel Fill links to Card Equipment via "card_equipment" (default is "equipment").
		# v3.0.0: a transport lists its machines in a child table (card_equipment), so every
		# machine of a multi-machine trip finds it, not only the first one
		"non_standard_fieldnames": {
			"Project Diesel Fill": "card_equipment",
			"Equipment Transport": "card_equipment",
			"Card Equipment Part": "card_equipment",
		},
		"transactions": [
			{
				"label": _("Operation"),
				"items": ["Card Monthly Card", "Card Equipment Assignment"],
			},
			{
				"label": _("Fuel & Transport"),
				"items": ["Project Diesel Fill", "Equipment Transport"],
			},
			# FR-077: parts that fit this machine (shown only to roles that read fitment rows)
			{
				"label": _("Parts fitment"),
				"items": ["Card Equipment Part"],
			},
			# Linked records this equipment points OUT to (resolved via internal_links).
			{
				"label": _("Linked records"),
				"items": ["Asset", "Supplier", "Project"],
			},
		],
		# Equipment -> record links, shown as linked documents (value of the link field).
		"internal_links": {
			"Asset": "الأصل_في_erpnext",
			"Supplier": "supplier",
			"Project": "current_project",
		},
		# Purchase Invoice / Sales Invoice are intentionally NOT listed here: they reach
		# Card Equipment through the accounting dimension added in O3.
	}
