# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe import _


def get_data():
	return {
		"fieldname": "equipment_model",
		"transactions": [
			{"label": _("Equipment"), "items": ["Card Equipment"]},
			{"label": _("Parts fitment"), "items": ["Card Equipment Part"]},
		],
	}
