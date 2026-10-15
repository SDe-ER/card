"""Desk dashboard connections added by CARD to standard doctypes.

Wired via ``override_doctype_dashboards`` in hooks.py. Frappe passes each app
the ALREADY-BUILT dashboard ``data`` (standard + any earlier app such as HRMS;
CARD is last in apps.txt). Every function here must therefore APPEND a "Card"
group and RETURN ``data`` -- never replace ``data["transactions"]`` or any
other key -- so connections contributed by ERPNext/HRMS survive.
"""

from frappe import _


def _prepare(data):
	"""Make sure ``data`` carries the two containers CARD appends to."""
	if not isinstance(data, dict):
		data = {}
	if not isinstance(data.get("transactions"), list):
		data["transactions"] = []
	if not isinstance(data.get("non_standard_fieldnames"), dict):
		data["non_standard_fieldnames"] = {}
	return data


def _append_card_group(data, links):
	"""Append one "Card" group and register the link fieldnames.

	``links`` is a list of (doctype, link_fieldname) pairs. Fieldnames are
	set one key at a time so keys contributed by other apps are never lost.
	"""
	data = _prepare(data)
	data["transactions"].append({"label": _("Card"), "items": [doctype for doctype, _f in links]})
	for doctype, fieldname in links:
		data["non_standard_fieldnames"][doctype] = fieldname
	return data


def supplier_dashboard(data):
	return _append_card_group(
		data,
		[
			("Card Equipment", "supplier"),
			("Card Monthly Card", "supplier"),
			("Project Diesel Fill", "supplier"),
			("Equipment Transport", "transport_supplier"),
		],
	)


def asset_dashboard(data):
	return _append_card_group(data, [("Card Equipment", "الأصل_في_erpnext")])


def project_dashboard(data):
	return _append_card_group(
		data,
		[
			("Card Monthly Card", "project"),
			("Card Equipment Assignment", "project"),
			("Project Diesel Fill", "project"),
			("Equipment Transport", "project"),
			("Card Equipment", "current_project"),
		],
	)


def customer_dashboard(data):
	return _append_card_group(
		data,
		[
			("Card Equipment Customer", "customer"),
			("Card Monthly Card", "customer"),
		],
	)
