# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe import _


def get_data():
	return {
		"heatmap": True,
		"heatmap_message": _("ساعات التشغيل اليومية من كروت التشغيل الشهرية"),
		"fieldname": "equipment",
		"transactions": [
			{
				"label": _("التشغيل"),
				"items": ["Card Monthly Card", "Card Equipment Assignment"],
			},
		],
	}
