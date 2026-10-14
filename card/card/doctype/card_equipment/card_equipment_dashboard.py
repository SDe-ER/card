# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe import _


def get_data():
	return {
		"heatmap": True,
		"heatmap_message": _("Daily operating hours from the monthly operation cards"),
		"fieldname": "equipment",
		"transactions": [
			{
				"label": _("Operation"),
				"items": ["Card Monthly Card", "Card Equipment Assignment"],
			},
		],
	}
