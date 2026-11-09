# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Value of a monthly card for the CARD dashboard (FR-122, Owner 2026-11-10).

Every card shows its value, whatever the equipment's ownership:

- rented from a supplier (مستأجَرة من مورد, إيجار من الباطن): the supplier net amount (cost);
- rented out to a customer (مؤجَّرة لعميل, إيجار من الباطن): the customer net amount (billing value);
- owned or managed equipment (ملك, طرف ثالث) with an internal operating rate: hours (or working days) x that
  rate (internal value).

Each value stays in its own series; one card can carry two of them (an owned crusher rented to a customer with
an internal rate), and they are never added into one number. A card with no supplier or customer side and no
internal rate still counts: it is listed as a card without an internal rate, with its hours.

Display and analysis only: nothing here writes a document or a GL entry. Every read goes through
``frappe.get_list``, so DocType permissions, Company User Permissions and field levels apply. The internal rate is
a level-2 field of Card Equipment: a user who cannot read it gets no internal series and no missing-rate count.
"""

import frappe
from frappe import _
from frappe.model import get_permitted_fields
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate
from frappe.utils.dateutils import (
	get_dates_from_timegrain,
	get_from_date_from_timespan,
	get_period,
	get_period_beginning,
)

from card.constants import (
	CUSTOMER_BILLING_DIRECTIONS,
	OWNED,
	SUPPLIER_BILLING_DIRECTIONS,
	THIRD_PARTY,
	derive_direction,
)

CARD = "Card Monthly Card"
EQUIPMENT = "Card Equipment"
PER_DAY = "باليوم"
INTERNAL_OWNERSHIPS = (OWNED, THIRD_PARTY)
RATE_FIELDS = ("internal_rate", "internal_rate_basis", "internal_hourly_rate")
CARD_FIELDS = (
	"name",
	"company",
	"equipment",
	"from_date",
	"ownership",
	"card_direction",
	"net_amount",
	"customer_net_amount",
	"total_working_hours",
	"working_days",
)
SERIES = ("supplier", "customer", "internal")


def series_labels():
	return {
		"supplier": _("Rental cost from suppliers"),
		"customer": _("Operating value for customers"),
		"internal": _("Internal operating value (owned or managed equipment)"),
	}


def internal_rate_of(equipment):
	"""(rate, per_day) of an equipment row. ``internal_rate`` with its basis wins; an equipment that only has
	the older ``internal_hourly_rate`` is valued per hour with it. (0, False) when neither is set."""
	if not equipment:
		return 0.0, False
	rate = flt(equipment.get("internal_rate"))
	if rate > 0:
		return rate, equipment.get("internal_rate_basis") == PER_DAY
	hourly = flt(equipment.get("internal_hourly_rate"))
	if hourly > 0:
		return hourly, False
	return 0.0, False


def card_value(card, equipment=None, with_internal=True):
	"""Dashboard values of one card. ``equipment`` is its Card Equipment row (internal rate fields) or None.

	Returns {"supplier", "customer", "internal": amounts, "missing_rate": bool, "hours": float}. ``internal``
	is None and ``missing_rate`` False when ``with_internal`` is False (the user cannot read the rate)."""
	direction = card.get("card_direction") or derive_direction(card.get("ownership"))
	hours = flt(card.get("total_working_hours"))
	value = {
		"supplier": flt(card.get("net_amount"), 2) if direction in SUPPLIER_BILLING_DIRECTIONS else 0.0,
		"customer": flt(card.get("customer_net_amount"), 2)
		if direction in CUSTOMER_BILLING_DIRECTIONS
		else 0.0,
		"internal": None,
		"missing_rate": False,
		"hours": hours,
	}
	if not with_internal:
		return value
	value["internal"] = 0.0
	rate, per_day = (
		internal_rate_of(equipment) if card.get("ownership") in INTERNAL_OWNERSHIPS else (0.0, False)
	)
	if rate > 0:
		quantity = flt(card.get("working_days")) if per_day else hours
		value["internal"] = flt(quantity * rate, 2)
	elif direction not in SUPPLIER_BILLING_DIRECTIONS and direction not in CUSTOMER_BILLING_DIRECTIONS:
		# internal operation without a rate: no amount to show, but the card and its hours still count
		value["missing_rate"] = True
	return value


def can_read_internal_rate(user=None):
	"""True when the user may read Card Equipment and its internal rate fields (level 2)."""
	if not frappe.has_permission(EQUIPMENT, "read", user=user):
		return False
	permitted = set(get_permitted_fields(EQUIPMENT, user=user))
	return all(field in permitted for field in RATE_FIELDS)


def get_card_values(from_date, to_date, company=None, include_drafts=False):
	"""Cards whose month starts between the two dates, with their dashboard values, as the session user may
	read them. Raises PermissionError when the user cannot read monthly cards."""
	frappe.has_permission(CARD, "read", throw=True)
	filters = [
		[CARD, "docstatus", "in", [0, 1] if include_drafts else [1]],
		[CARD, "from_date", ">=", getdate(from_date)],
		[CARD, "from_date", "<=", getdate(to_date)],
	]
	if company:
		filters.append([CARD, "company", "=", company])
	cards = frappe.get_list(
		CARD, fields=list(CARD_FIELDS), filters=filters, order_by="from_date asc", limit=0
	)

	with_internal = can_read_internal_rate()
	equipment = {}
	names = sorted({c.equipment for c in cards if c.equipment and c.ownership in INTERNAL_OWNERSHIPS})
	if with_internal and names:
		equipment = {
			row.name: row
			for row in frappe.get_list(
				EQUIPMENT, fields=["name", *RATE_FIELDS], filters={"name": ["in", names]}, limit=0
			)
		}
	for card in cards:
		card.update(card_value(card, equipment.get(card.equipment), with_internal))
	return cards, with_internal


def totals(cards):
	out = {key: 0.0 for key in SERIES}
	out.update(missing_rate_cards=0, missing_rate_hours=0.0)
	for card in cards:
		for key in SERIES:
			out[key] = flt(out[key] + flt(card.get(key)), 2)
		if card.get("missing_rate"):
			out["missing_rate_cards"] += 1
			out["missing_rate_hours"] = flt(out["missing_rate_hours"] + flt(card.get("hours")), 2)
	return out


def bucket_by_period(cards, from_date, to_date, timegrain="Monthly"):
	"""(labels, {series: [values]}) per period of ``timegrain`` from ``from_date`` to ``to_date``."""
	ends = [getdate(d) for d in get_dates_from_timegrain(from_date, to_date, timegrain)]
	values = {key: [0.0] * len(ends) for key in SERIES}
	for card in cards:
		day = getdate(card.from_date)
		index = next((i for i, end in enumerate(ends) if day <= end), None)
		if index is None:
			continue
		for key in SERIES:
			values[key][index] = flt(values[key][index] + flt(card.get(key)), 2)
	return [get_period(end, timegrain) for end in ends], values


def _filters(filters):
	filters = frappe.parse_json(filters) if filters else {}
	return filters if isinstance(filters, dict) else {}


def _last_month():
	start = get_first_day(add_months(nowdate(), -1))
	return start, get_last_day(start)


def _last_month_totals(filters):
	filters = _filters(filters)
	start, end = _last_month()
	cards, with_internal = get_card_values(
		start, end, company=filters.get("company"), include_drafts=bool(filters.get("include_drafts"))
	)
	return totals(cards), with_internal, start, end


def _route(start, end, **route_options):
	return {
		"route": ["List", CARD],
		"route_options": {"docstatus": 1, "from_date": ["between", [str(start), str(end)]], **route_options},
	}


# Number Cards (type Custom). Frappe's number card widget calls its method with frappe.xcall, which always
# sends POST, so these side-effect-free reads accept POST only (a GET-only method would not load on the
# workspace). They read nothing they do not return and write nothing.


@frappe.whitelist(methods=["POST"])
def supplier_cost_last_month(filters=None):
	result, _w, start, end = _last_month_totals(filters)
	return {"value": result["supplier"], "fieldtype": "Currency", **_route(start, end)}


@frappe.whitelist(methods=["POST"])
def customer_value_last_month(filters=None):
	result, _w, start, end = _last_month_totals(filters)
	return {"value": result["customer"], "fieldtype": "Currency", **_route(start, end)}


@frappe.whitelist(methods=["POST"])
def internal_value_last_month(filters=None):
	result, with_internal, start, end = _last_month_totals(filters)
	return {
		"value": result["internal"] if with_internal else None,
		"fieldtype": "Currency",
		**_route(start, end),
	}


@frappe.whitelist(methods=["POST"])
def cards_without_internal_rate_last_month(filters=None):
	result, with_internal, start, end = _last_month_totals(filters)
	return {
		"value": result["missing_rate_cards"] if with_internal else None,
		"fieldtype": "Int",
		**_route(start, end),
	}


@frappe.whitelist(methods=["POST"])
def hours_without_internal_rate_last_month(filters=None):
	result, with_internal, start, end = _last_month_totals(filters)
	return {
		"value": result["missing_rate_hours"] if with_internal else None,
		"fieldtype": "Float",
		**_route(start, end),
	}


def chart_data(chart, filters=None, from_date=None, to_date=None, timespan=None, time_interval=None):
	"""Labels and one dataset per series for the monthly card values chart."""
	filters = _filters(filters)
	timegrain = time_interval or chart.get("time_interval") or "Monthly"
	timespan = timespan or chart.get("timespan") or "Last Year"
	if timespan == "Select Date Range":
		from_date = from_date or chart.get("from_date")
		to_date = to_date or chart.get("to_date")
	to_date = getdate(to_date or nowdate())
	if not from_date:
		from_date = get_from_date_from_timespan(to_date, timespan)
	from_date = get_period_beginning(getdate(from_date), timegrain)

	cards, with_internal = get_card_values(
		from_date, to_date, company=filters.get("company"), include_drafts=bool(filters.get("include_drafts"))
	)
	labels, values = bucket_by_period(cards, from_date, to_date, timegrain)
	names = series_labels()
	series = SERIES if with_internal else ("supplier", "customer")
	return {
		"labels": labels,
		"datasets": [{"name": names[key], "values": values[key]} for key in series],
	}
