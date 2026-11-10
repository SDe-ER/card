# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-151 (#31): Diesel Variance Anomaly report. Read-only; no accounting, nothing is written.

One row per equipment and calendar month (clipped to the selected dates) of ONE company:

- Filled litres: the litres of the company's SUBMITTED Project Diesel Fills charged directly to the equipment
  (``card_equipment`` set). This is the "recorded" part of ``card.diesel.allocate_project_diesel``, by the same
  rule (a direct fill counts in full for its equipment). Project-tank fills (no equipment) are NOT split across
  machines: owner decision 2026-11-10 on #31 (#118 rule 7) — a machine gets litres only from a measured fill. Their
  litres are shown once, as a project-level summary figure, never per equipment.
- Hours and their basis:
  - "Engine hours": from the submitted Equipment Meter Readings (FR-140) of the company, when the readings cover
    the whole month (a reading at or before its start, one at or after its end, no meter reset in between). Each
    interval's hours are spread evenly over its time to apply the rate of each day. The nature is "Recorded" when
    readings fall exactly on the month's limits and every interval has one rate; otherwise "Estimated" (time
    proration).
  - "Billable-hours proxy": otherwise, the operating hours of the days of the company's submitted monthly cards
    (``working_hours`` of each day row). Always "Estimated": billable hours stand in for engine hours. With a
    project filter the proxy is always used, as engine hours belong to the equipment, not to a project.
- Expected litres: Σ over the days (hours of the day × the FR-144 consumption rate valid on that day), with the
  rate order of ``card.consumption.consumption_rate_details`` (equipment row, daily standard, static, type row of
  the equipment's company, type row with no company), resolved in memory from batched reads. A day with hours and
  no rate leaves the expected side empty and flags the row (never a crash, never an invented rate).
- Variance = filled − expected (litres, %, and cost at the month's average direct-fill price). A variance is an
  analytical signal, NOT a loss; this report makes no loss claim (loss comes only from tank dips, a later WP).
- Anomaly flags come only from the company's row in Card Settings ``diesel_variance_thresholds``; with no row (the
  default) nothing is flagged as an anomaly. Data notes (no rate, proxy used) are always shown.

Access: the report roles of Equipment Diesel Analysis; one company the user may see for the doctypes read
(``card.report_access.resolve_company``). Rates and every figure derived from them need level-1 read on Card
Equipment (the level of the rates); amounts need read on the fill amount's level. Columns a user may not read are
removed, never sent. Every read is batched (a fixed number of queries whatever the number of rows)."""

from collections import defaultdict
from datetime import datetime, time, timedelta
from itertools import pairwise

import frappe
from frappe import _
from frappe.query_builder.functions import Max, Min, Sum
from frappe.utils import add_days, cint, date_diff, flt, get_first_day, get_last_day, getdate, nowdate

from card.report_access import readable_links, resolve_company
from card.report_currency import company_currency, label_currency

DOCTYPES = ("Card Monthly Card", "Project Diesel Fill", "Equipment Meter Reading")
FILL = "Project Diesel Fill"
EQUIPMENT = "Card Equipment"
READING = "Equipment Meter Reading"
THRESHOLD_TABLE = "diesel_variance_thresholds"
THRESHOLD_DOCTYPE = "Card Diesel Variance Threshold"
MAX_DAYS = 366

RATE_FIELDS = (
	"rate",
	"rate_source",
	"expected_litres",
	"expected_nature",
	"variance_litres",
	"variance_pct",
	"variance_cost",
)
AMOUNT_FIELDS = ("filled_amount", "variance_cost")


def rate_source_label(source):
	"""A CARD-specific label for a ``card.consumption`` rate source."""
	from card.consumption import SOURCE_DAILY, SOURCE_EQUIPMENT, SOURCE_STATIC, SOURCE_TYPE

	return {
		SOURCE_EQUIPMENT: _("Dated rate of the equipment"),
		SOURCE_DAILY: _("Daily diesel standard of the equipment"),
		SOURCE_STATIC: _("Static expected consumption of the equipment"),
		SOURCE_TYPE: _("Default rate of the equipment type"),
	}.get(source, source)


def basis_engine():
	return _("Engine hours (meter readings)")


def basis_proxy():
	return _("Billable-hours proxy (card hours)")


def nature_recorded():
	return _("Recorded figure")


def nature_estimated():
	return _("Estimated figure")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, *DOCTYPES)
	filters.company = company
	start, end = _period(filters)
	show_rates = 1 in frappe.get_meta(EQUIPMENT).get_permlevel_access("read")
	amount_level = cint(frappe.get_meta(FILL).get_field("amount").permlevel)
	show_amounts = amount_level in frappe.get_meta(FILL).get_permlevel_access("read")

	fills, tank = _direct_fills(filters, start, end)
	card_hours = _card_hours(filters, start, end)
	readings = {} if filters.get("project") else _readings(filters, start, end)
	equipment = set(fills) | set(card_hours) | set(readings)
	info = _equipment_info(equipment, filters)
	equipment = set(info)
	book = RateBook(info) if equipment else None
	threshold = _threshold(company)

	rows = []
	for eq in sorted(equipment, key=lambda e: ((info[e].equipment_name or e), e)):
		meter = EngineHours(readings.get(eq) or [])
		for p_start, p_end in _months(start, end):
			row = _row(eq, info[eq], p_start, p_end, fills.get(eq), card_hours.get(eq), meter, book, filters)
			if row is None:
				continue
			_flag(row, threshold, show_rates)
			rows.append(row)

	columns = _columns()
	summary = _summary(rows, tank)
	if not show_rates:
		_strip(columns, rows, summary, RATE_FIELDS)
	if not show_amounts:
		_strip(columns, rows, summary, AMOUNT_FIELDS)
	for row in rows:
		row.pop("_filled_raw", None)
	message = _message(show_rates, threshold)
	result = [readable_links(columns, rows), rows, message, None, summary, True]
	return label_currency(result, company_currency(company))


# ---------- filters and periods ----------


def _period(filters):
	start = getdate(filters.get("from_date") or get_first_day(nowdate()))
	end = getdate(filters.get("to_date") or nowdate())
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))
	if date_diff(end, start) + 1 > MAX_DAYS:
		frappe.throw(
			_("Select a period of at most {0} days for the diesel variance report.").format(MAX_DAYS)
		)
	return start, end


def _months(start, end):
	"""(first day, last day) of each calendar month between start and end, clipped to them."""
	out = []
	cursor = start
	while cursor <= end:
		last = min(getdate(get_last_day(cursor)), end)
		out.append((cursor, last))
		cursor = add_days(last, 1)
	return out


def _month_key(day):
	return "%04d-%02d" % (day.year, day.month)


# ---------- batched reads ----------


def _direct_fills(filters, start, end):
	"""({equipment: {month: {"litres", "amount", "projects"}}}, project-tank totals). One query."""
	conditions = {
		"company": filters.company,
		"docstatus": 1,
		"date": ["between", [start, end]],
	}
	if filters.get("project"):
		conditions["project"] = filters.project
	if filters.get("equipment"):
		# one equipment: its direct fills only (project-tank fills belong to no equipment)
		conditions["card_equipment"] = filters.equipment
	rows = frappe.get_all(
		FILL,
		filters=conditions,
		fields=["card_equipment", "date", "litres", "amount", "project"],
		limit_page_length=0,
	)
	out = defaultdict(dict)
	tank = {"litres": 0.0, "amount": 0.0, "count": 0}
	for r in rows:
		if not r.card_equipment:
			tank["litres"] += flt(r.litres)
			tank["amount"] += flt(r.amount)
			tank["count"] += 1
			continue
		month = out[r.card_equipment].setdefault(
			_month_key(getdate(r.date)), {"litres": 0.0, "amount": 0.0, "projects": set()}
		)
		month["litres"] += flt(r.litres)
		month["amount"] += flt(r.amount)
		if r.project:
			month["projects"].add(r.project)
	return out, tank


def _card_hours(filters, start, end):
	"""{equipment: {date: {"hours", "projects"}}} from the day rows of SUBMITTED monthly cards of the company
	(all shifts summed). One query."""
	card = frappe.qb.DocType("Card Monthly Card")
	day = frappe.qb.DocType("Card Monthly Card Day")
	query = (
		frappe.qb.from_(day)
		.join(card)
		.on(card.name == day.parent)
		.select(
			card.equipment, day.operation_date.as_("day"), card.project, Sum(day.working_hours).as_("hours")
		)
		.where(
			(day.parenttype == "Card Monthly Card")
			& (day.parentfield == "days")
			& (card.company == filters.company)
			& (card.docstatus == 1)
			& day.operation_date.between(start, end)
			& (day.working_hours > 0)
		)
		.groupby(card.equipment, day.operation_date, card.project)
	)
	if filters.get("project"):
		query = query.where(card.project == filters.project)
	if filters.get("equipment"):
		query = query.where(card.equipment == filters.equipment)
	out = defaultdict(dict)
	for r in query.run(as_dict=True):
		entry = out[r.equipment].setdefault(getdate(r.day), {"hours": 0.0, "projects": set()})
		entry["hours"] += flt(r.hours)
		if r.project:
			entry["projects"].add(r.project)
	return out


def _readings(filters, start, end):
	"""{equipment: [reading rows sorted by time]}: the company's submitted readings inside the period plus, per
	equipment, the last one before it and the first one after it. Four queries."""
	p_start = datetime.combine(start, time.min)
	p_end = datetime.combine(add_days(end, 1), time.min)
	reading = frappe.qb.DocType(READING)
	scope = (reading.docstatus == 1) & (reading.company == filters.company)
	if filters.get("equipment"):
		scope = scope & (reading.equipment == filters.equipment)
	fields = (
		reading.name,
		reading.equipment,
		reading.reading_datetime,
		reading.engine_hours,
		reading.is_meter_reset,
		reading.creation,
	)
	inside = (
		frappe.qb.from_(reading)
		.select(*fields)
		.where(scope & (reading.reading_datetime >= p_start) & (reading.reading_datetime <= p_end))
		.run(as_dict=True)
	)
	# the nearest reading on each side of the period, per equipment
	edges = set()
	for condition, edge in (
		(reading.reading_datetime < p_start, Max),
		(reading.reading_datetime > p_end, Min),
	):
		for r in (
			frappe.qb.from_(reading)
			.select(reading.equipment, edge(reading.reading_datetime).as_("at"))
			.where(scope & condition)
			.groupby(reading.equipment)
			.run(as_dict=True)
		):
			edges.add((r.equipment, r.at))
	outside = []
	if edges:
		outside = [
			r
			for r in frappe.qb.from_(reading)
			.select(*fields)
			.where(
				scope
				& reading.equipment.isin(sorted({e for e, _at in edges}))
				& reading.reading_datetime.isin(sorted({at for _e, at in edges}))
			)
			.run(as_dict=True)
			if (r.equipment, r.reading_datetime) in edges
		]
	out = defaultdict(dict)
	for r in inside + outside:
		out[r.equipment][r.name] = r
	return {
		eq: sorted(rows.values(), key=lambda r: (r.reading_datetime, r.creation)) for eq, rows in out.items()
	}


def _equipment_info(names, filters):
	if not names:
		return {}
	conditions = {"name": ["in", sorted(names)]}
	if filters.get("equipment_type"):
		conditions["equipment_type"] = filters.equipment_type
	rows = frappe.get_all(
		EQUIPMENT,
		filters=conditions,
		fields=[
			"name",
			"equipment_name",
			"company",
			"equipment_type",
			"expected_consumption",
			"daily_diesel_consumption",
			"daily_hours",
		],
		limit_page_length=0,
	)
	return {r.name: r for r in rows}


def _threshold(company):
	"""The company's anomaly thresholds, or None (no row = no anomaly flags). Server read of the setting."""
	rows = frappe.get_all(
		THRESHOLD_DOCTYPE,
		filters={
			"parent": "Card Settings",
			"parenttype": "Card Settings",
			"parentfield": THRESHOLD_TABLE,
			"company": company,
		},
		fields=[
			"variance_pct_threshold",
			"min_variance_litres",
			"flag_fill_without_hours",
			"flag_hours_without_fill",
		],
		limit=1,
	)
	if not rows:
		return None
	row = rows[0]
	if not (
		flt(row.variance_pct_threshold)
		or flt(row.min_variance_litres)
		or cint(row.flag_fill_without_hours)
		or cint(row.flag_hours_without_fill)
	):
		return None
	return row


# ---------- consumption rates (batched FR-144 resolution) ----------


class RateBook:
	"""The rate of ``card.consumption.consumption_rate_details`` for many equipment and days, from two queries."""

	def __init__(self, info):
		from card.consumption import (
			EQUIPMENT_ROW_DOCTYPE,
			EQUIPMENT_TABLE,
			SOURCE_DAILY,
			SOURCE_EQUIPMENT,
			SOURCE_STATIC,
			SOURCE_TYPE,
			TYPE_ROW_DOCTYPE,
			TYPE_TABLE,
		)

		self.sources = (SOURCE_EQUIPMENT, SOURCE_DAILY, SOURCE_STATIC, SOURCE_TYPE)
		self.info = info
		self.equipment_rows = defaultdict(list)
		for r in frappe.get_all(
			EQUIPMENT_ROW_DOCTYPE,
			filters={
				"parenttype": EQUIPMENT,
				"parentfield": EQUIPMENT_TABLE,
				"parent": ["in", sorted(info)],
			},
			fields=["parent", "valid_from", "litres_per_hour", "idx"],
			order_by="valid_from desc, idx desc",
			limit_page_length=0,
		):
			if r.valid_from:
				self.equipment_rows[r.parent].append(r)
		types = sorted({i.equipment_type for i in info.values() if i.equipment_type})
		self.type_rows = defaultdict(list)
		if types:
			for r in frappe.get_all(
				TYPE_ROW_DOCTYPE,
				filters={
					"parenttype": "Card Equipment Type",
					"parentfield": TYPE_TABLE,
					"parent": ["in", types],
				},
				fields=["parent", "company", "valid_from", "litres_per_hour", "idx"],
				order_by="valid_from desc, idx desc",
				limit_page_length=0,
			):
				if r.valid_from:
					self.type_rows[r.parent].append(r)

	@staticmethod
	def _first(rows, day, company=None, any_company=False):
		for r in rows:
			if getdate(r.valid_from) > day:
				continue
			if any_company or (r.get("company") or None) == company:
				return r
		return None

	def rate(self, equipment, day):
		"""(rate or None, source or None) on ``day``, in the order of consumption_rate_details."""
		src_equipment, src_daily, src_static, src_type = self.sources
		values = self.info[equipment]
		row = self._first(self.equipment_rows.get(equipment) or [], day, any_company=True)
		if row:
			return flt(row.litres_per_hour), src_equipment
		if flt(values.daily_diesel_consumption) and flt(values.daily_hours) > 0:
			return flt(values.daily_diesel_consumption) / flt(values.daily_hours), src_daily
		if flt(values.expected_consumption):
			return flt(values.expected_consumption), src_static
		if values.equipment_type:
			rows = self.type_rows.get(values.equipment_type) or []
			row = None
			if values.company:
				row = self._first(rows, day, company=values.company)
			if not row:
				row = self._first(rows, day, company=None)
			if row:
				return flt(row.litres_per_hour), src_type
		return None, None


# ---------- engine hours from meter readings ----------


class EngineHours:
	"""Engine hours of one equipment from its sorted submitted readings. An interval between two consecutive
	readings carries ``later - earlier`` hours, spread evenly over its time; an interval that ends on a meter
	reset carries no known hours (it breaks the coverage)."""

	def __init__(self, readings):
		self.intervals = []
		for prev, nxt in pairwise(readings):
			t0, t1 = prev.reading_datetime, nxt.reading_datetime
			if t1 <= t0:
				continue
			hours = flt(nxt.engine_hours) - flt(prev.engine_hours)
			valid = not cint(nxt.is_meter_reset) and hours >= 0
			self.intervals.append((t0, t1, hours if valid else None))

	def for_period(self, p_start, p_end):
		"""({day: hours}, exact) when valid intervals cover [p_start 00:00, p_end + 1 day 00:00) completely,
		else None. ``exact`` is True when no interval crosses the period's limits (no proration needed at the
		limits)."""
		lo = datetime.combine(p_start, time.min)
		hi = datetime.combine(add_days(p_end, 1), time.min)
		overlapping = [i for i in self.intervals if i[1] > lo and i[0] < hi]
		if not overlapping or overlapping[0][0] > lo or overlapping[-1][1] < hi:
			return None
		if any(hours is None for _t0, _t1, hours in overlapping):
			return None
		for (_a0, a1, _h1), (b0, _b1, _h2) in pairwise(overlapping):
			if b0 != a1:  # defensive: consecutive readings always touch
				return None
		exact = overlapping[0][0] == lo and overlapping[-1][1] == hi
		days = {}
		day = p_start
		while day <= p_end:
			d0 = datetime.combine(day, time.min)
			d1 = d0 + timedelta(days=1)
			total = 0.0
			for t0, t1, hours in overlapping:
				overlap = (min(t1, d1) - max(t0, d0)).total_seconds()
				if overlap > 0:
					total += hours * overlap / (t1 - t0).total_seconds()
			days[day] = total
			day = add_days(day, 1)
		return days, exact, overlapping

	@staticmethod
	def days_of(interval, p_start, p_end):
		"""The period days an interval touches."""
		t0, t1, _hours = interval
		first = max(getdate(t0), p_start)
		last = min(getdate(t1 - timedelta(microseconds=1)), p_end)
		out = []
		day = first
		while day <= last:
			out.append(day)
			day = add_days(day, 1)
		return out


# ---------- rows ----------


def _row(eq, info, p_start, p_end, fills_by_month, card_days, meter, book, filters):
	month = _month_key(p_start)
	fill = (fills_by_month or {}).get(month) or {"litres": 0.0, "amount": 0.0, "projects": set()}
	billable = {d: v for d, v in (card_days or {}).items() if p_start <= d <= p_end}
	billable_hours = flt(sum(v["hours"] for v in billable.values()), 2)
	engine = None if filters.get("project") else meter.for_period(p_start, p_end)
	if not (fill["litres"] or fill["amount"] or billable_hours or engine):
		return None

	notes = []
	if engine:
		day_hours, exact, overlapping = engine
		basis = basis_engine()
	else:
		day_hours = {d: v["hours"] for d, v in billable.items()}
		exact = False
		overlapping = []
		basis = basis_proxy()
		if filters.get("project"):
			notes.append(
				_("Project filter: engine hours belong to the equipment, the billable-hours proxy is used")
			)
		elif billable_hours:
			notes.append(_("Meter readings do not cover the month: the billable-hours proxy is used"))

	hours = flt(sum(day_hours.values()), 2)
	expected = 0.0
	missing_rate = False
	sources = set()
	for day, h in sorted(day_hours.items()):
		if h <= 0:
			continue
		rate, source = book.rate(eq, day)
		if rate is None:
			missing_rate = True
			continue
		sources.add(source)
		expected += h * rate

	rate_split = False
	if engine:
		for interval in overlapping:
			rates = {book.rate(eq, d)[0] for d in EngineHours.days_of(interval, p_start, p_end)}
			if len(rates) > 1:
				rate_split = True
				break
	if missing_rate:
		notes.append(_("No consumption rate on some operating days: expected litres not computed"))
		expected = None
	else:
		expected = flt(expected, 3)
	# card hours and exact meter differences are recorded; hours prorated between readings are estimated
	hours_nature = nature_estimated() if engine and not exact else nature_recorded()
	if engine and exact and not rate_split:
		expected_nature = nature_recorded()
	else:
		expected_nature = nature_estimated()
	if engine and not exact:
		notes.append(_("Engine hours prorated by time between meter readings"))
	if rate_split:
		notes.append(_("The consumption rate changes between two meter readings: hours split by time"))

	filled = flt(fill["litres"], 3)
	variance = flt(filled - expected, 3) if expected is not None else None
	variance_pct = flt(variance / expected * 100, 2) if expected else None
	price = flt(fill["amount"]) / filled if filled else None
	variance_cost = flt(variance * price, 2) if variance is not None and price is not None else None
	projects = set(fill["projects"])
	for v in billable.values():
		projects |= v["projects"]

	return {
		"equipment": eq,
		"equipment_name": info.equipment_name or eq,
		"period": month,
		"projects": ", ".join(sorted(projects)),
		"engine_hours": flt(sum(day_hours.values()), 2) if engine else None,
		"billable_hours": billable_hours,
		"hours_basis": basis,
		"hours": hours,
		"hours_nature": hours_nature,
		"rate": flt(expected / hours, 3) if expected is not None and hours else None,
		"rate_source": ", ".join(sorted(rate_source_label(s) for s in sources)),
		"expected_litres": expected,
		"expected_nature": expected_nature,
		"filled_litres": filled,
		"filled_nature": nature_recorded(),
		"filled_amount": flt(fill["amount"], 2),
		"variance_litres": variance,
		"variance_pct": variance_pct,
		"variance_cost": variance_cost,
		"anomaly": "",
		"notes": "; ".join(notes),
	}


def _flag(row, threshold, show_rates=True):
	"""Anomaly flags from the company's thresholds only (none without a row). The variance flag is derived from
	the rates, so a user who may not read them does not get it either."""
	if not threshold:
		return
	flags = []
	pct = flt(threshold.variance_pct_threshold)
	litres = flt(threshold.min_variance_litres)
	variance = row.get("variance_litres")
	# a month with no hours or no fill gets its own flag below, not a variance percentage as well
	if show_rates and (pct or litres) and variance and row.get("expected_litres") and row["filled_litres"]:
		pct_hit = not pct or abs(flt(row.get("variance_pct"))) >= pct
		litres_hit = not litres or abs(variance) >= litres
		if pct_hit and litres_hit:
			flags.append(_("Variance above the company threshold"))
	if cint(threshold.flag_fill_without_hours) and row["filled_litres"] and not row["hours"]:
		flags.append(_("Diesel fill without operating hours"))
	if cint(threshold.flag_hours_without_fill) and row["hours"] and not row["filled_litres"]:
		flags.append(_("Operating hours without a diesel fill"))
	row["anomaly"] = "; ".join(flags)


def _strip(columns, rows, summary, keys):
	columns[:] = [c for c in columns if c.get("fieldname") not in keys]
	for row in rows:
		for key in keys:
			row.pop(key, None)
	summary[:] = [t for t in summary if t.get("key") not in keys]


def _columns():
	def col(fieldname, label, fieldtype="Data", width=110, **extra):
		return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width, **extra}

	return [
		col("equipment_name", _("Equipment name"), width=180),
		col("equipment", _("Equipment number"), "Link", options=EQUIPMENT),
		col("period", _("Operating month"), width=85),
		col("projects", _("Projects of the fills and cards"), width=140),
		col("engine_hours", _("Engine hours (meter readings)"), "Float", precision=2),
		col("billable_hours", _("Billable hours (cards)"), "Float", precision=2),
		col("hours_basis", _("Hours basis"), width=160),
		col("hours", _("Hours used for expected litres"), "Float", precision=2),
		col("hours_nature", _("Hours nature"), width=110),
		col("rate", _("Average consumption rate (litres/hour)"), "Float", precision=3),
		col("rate_source", _("Consumption rate source"), width=130),
		col("expected_litres", _("Expected litres"), "Float", precision=3),
		col("expected_nature", _("Expected litres nature"), width=110),
		col("filled_litres", _("Filled litres (direct fills)"), "Float", precision=3),
		col("filled_nature", _("Filled litres nature"), width=110),
		col("filled_amount", _("Direct fills amount"), "Currency"),
		col("variance_litres", _("Variance litres (filled - expected, not a loss)"), "Float", precision=3),
		col("variance_pct", _("Variance %"), "Percent", width=90),
		col("variance_cost", _("Variance cost at the average fill price (not a loss)"), "Currency"),
		col("anomaly", _("Anomaly flags"), width=200),
		col("notes", _("Data notes"), width=260),
	]


def _summary(rows, tank):
	expected = flt(sum(r["expected_litres"] or 0 for r in rows), 3)
	filled = flt(sum(r["filled_litres"] for r in rows), 3)
	variance = flt(sum(r["variance_litres"] or 0 for r in rows), 3)
	flagged = sum(1 for r in rows if r["anomaly"])
	return [
		{"key": "expected_litres", "label": _("Expected litres"), "value": expected, "datatype": "Float"},
		{
			"key": "filled_litres",
			"label": _("Filled litres (direct fills)"),
			"value": filled,
			"datatype": "Float",
		},
		{
			"key": "filled_amount",
			"label": _("Direct fills amount"),
			"value": flt(sum(r["filled_amount"] for r in rows), 2),
			"datatype": "Currency",
		},
		{
			"key": "variance_litres",
			"label": _("Variance litres (filled - expected, not a loss)"),
			"value": variance,
			"datatype": "Float",
			"indicator": "Orange" if variance else "Blue",
		},
		{
			"key": "anomaly",
			"label": _("Rows with anomaly flags"),
			"value": flagged,
			"datatype": "Int",
			"indicator": "Red" if flagged else "Green",
		},
		{
			"key": "tank_litres",
			"label": _("Project-tank fill litres (not attributed to any equipment)"),
			"value": flt(tank["litres"], 3),
			"datatype": "Float",
		},
	]


def _message(show_rates, threshold):
	variance = _(
		"Variance = filled litres (direct fills recorded for the equipment) minus expected litres (hours x the"
		" consumption rate valid on each day). A variance is an analytical signal, not a fuel loss; this"
		" report makes no loss claim."
	)
	basis = _(
		"Hours basis: engine hours from meter readings when they cover the whole month, otherwise the"
		" billable-hours proxy (card hours), an estimate."
	)
	parts = [
		variance,
		basis,
		_(
			"Project-tank fills are not split across equipment; their litres are shown once, as a project-level figure."
		),
	]
	if not threshold:
		parts.append(
			_("No anomaly thresholds are set for this company in Card Settings: nothing is flagged.")
		)
	if not show_rates:
		parts.append(_("Consumption rates and the figures derived from them are hidden for your role."))
	return " ".join(parts)
