# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe import _


def get_data():
	return {
		"fieldname": "equipment_make",
		"transactions": [
			{"label": _("Equipment"), "items": ["Card Equipment Model", "Card Equipment"]},
		],
	}
