# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Dashboard Chart Source "Card Monthly Values" (FR-111): the value of every monthly card per month, in three
series (supplier rental cost, customer operating value, internal operating value). See card.card_value."""

import frappe

from card.card_value import chart_data


# Frappe's chart widget calls the source method with frappe.xcall, which always sends POST; the method only
# reads. It is not wrapped in frappe.utils.dashboard.cache_source: that cache is keyed by the chart name only,
# so one user's totals would be served to users of other companies.
@frappe.whitelist(methods=["POST"])
def get(
	chart_name: str | None = None,
	chart: str | dict | None = None,
	no_cache: bool | int | str | None = None,
	filters: str | dict | list | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	timespan: str | None = None,
	time_interval: str | None = None,
	heatmap_year: str | int | None = None,
	refresh: bool | int | str | None = None,
) -> dict:
	if chart_name:
		chart = frappe.get_doc("Dashboard Chart", chart_name)
		chart.check_permission("read")
	else:
		chart = frappe._dict(frappe.parse_json(chart) or {})
	return chart_data(
		chart,
		filters=filters if filters not in (None, "", "null") else chart.get("filters_json"),
		from_date=from_date,
		to_date=to_date,
		timespan=timespan,
		time_interval=time_interval,
	)
