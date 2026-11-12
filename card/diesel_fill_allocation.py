# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-157 (#31, #47, #124; closure plan WP-G1, C-03, C-06): compute the per-equipment Diesel
Fill Allocation rows of a tank-style project diesel fill, frozen at submit.

Report/card display only: the GL posting of the fill is unchanged (FR-100: a tank fill posts
ONE project-level line, never per equipment). This module decides, on submit, how a tank fill's
litres are split for a report or a card. The rule is one of two per-company options:

- ``Hours (tank estimate)`` (default, FR-033): each equipment's share =
  equipment_hours / Σ hours × total_litres.
- ``Hours × Rate (tank estimate)``: share = (hours × rate) / Σ (hours × rate) × total_litres,
  with rate = ``card.consumption.consumption_rate`` on the fill date, or 0 when none resolves.

Equipment universe: every equipment that has a submitted Card Monthly Card on the fill's
project and month, plus every matched Card Equipment on the fill's `equipment_filled` list.
A fill with `card_equipment` set (one measured equipment) is NOT tank-style; no rows are
written for it.

Zero weight (hours = 0 OR, for Hours × Rate, rate = 0): the row is written with
``allocated_litres = 0``, ``review_flag = 1`` and kept out of the share basis. The
largest positive row absorbs the rounding remainder (``remainder = 1``). When every row has
zero weight no rows are written and the parent's ``allocation_review`` field records the
reason, so a reader shows the legacy FR-033 estimate instead.

No backfill (C-06): the rows are written at ``before_submit`` only; fills submitted before
FR-157 keep the FR-033 read-time estimate.

No GL change (FR-100): nothing in this module reaches ``card.gl.posting`` or writes GL entries.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, getdate, now_datetime

from card.consumption import consumption_rate
from card.diesel import _month_year, project_operating_hours, split_by_weights

TABLE = "diesel_fill_allocation"
LITRES_PRECISION = 3
HOURS_WEIGHTING = "Hours (tank estimate)"
HOURS_RATE_WEIGHTING = "Hours × Rate (tank estimate)"
WEIGHTING_OPTIONS = (HOURS_WEIGHTING, HOURS_RATE_WEIGHTING)

BASIS_ESTIMATED = "estimated"
RULE_HOURS = "hours"
RULE_HOURS_RATE = "hours×rate"


def _weighting_of_company(company: str | None) -> str:
	"""Resolve the per-company tank estimate weighting; empty company or missing value = default."""
	from card.settings import company_setting

	value = company_setting(company, "tank_estimate_weighting") if company else None
	if value in WEIGHTING_OPTIONS:
		return value
	return HOURS_WEIGHTING


def _rule_tag(weighting: str) -> str:
	return RULE_HOURS_RATE if weighting == HOURS_RATE_WEIGHTING else RULE_HOURS


def _listed_equipment(fill) -> set[str]:
	"""Matched equipment names on the fill's ``equipment_filled`` list."""
	names: set[str] = set()
	for row in fill.get("equipment_filled") or []:
		if row.get("card_equipment"):
			names.add(row.card_equipment)
	return names


def _universe(fill, hours_map: dict[str, float]) -> list[str]:
	"""The equipment considered for the split, sorted deterministically: every equipment with
	cards in the project+month, plus every matched listed equipment. Equipment of another
	company is dropped (the parent already refuses cross-company rows on save)."""
	names = set(hours_map.keys()) | _listed_equipment(fill)
	names.discard(None)
	names.discard("")
	if not names:
		return []
	# drop equipment of another company; the parent validated the direct links already
	same_company = frappe.get_all(
		"Card Equipment",
		filters={"name": ["in", sorted(names)], "company": fill.company},
		pluck="name",
	)
	return sorted(same_company)


def _row_rates(equipment_names: list[str], on_date) -> dict[str, float]:
	"""Litres per operating hour of each equipment on ``on_date`` from ``card.consumption``. A
	missing or zero rate stays 0 (the caller flags the row for review)."""
	rates: dict[str, float] = {}
	day = getdate(on_date)
	for name in equipment_names:
		rate = consumption_rate(name, day) or 0
		rates[name] = flt(rate)
	return rates


def _weights(
	equipment_names: list[str],
	hours_map: dict[str, float],
	rates_map: dict[str, float],
	weighting: str,
) -> dict[str, float]:
	"""Return the positive weight of each equipment under the chosen weighting. Equipment with
	zero weight is NOT returned (its row carries no litres and is flagged for review)."""
	weights: dict[str, float] = {}
	for name in equipment_names:
		hours = flt(hours_map.get(name) or 0)
		rate = flt(rates_map.get(name) or 0)
		if hours <= 0:
			continue
		if weighting == HOURS_RATE_WEIGHTING:
			weight = hours * rate
			if weight <= 0:
				continue
			weights[name] = weight
		else:
			weights[name] = hours
	return weights


def plan_allocation(fill) -> dict:
	"""Return the allocation plan for a tank-style fill, or ``None`` when no row is written.

	Shape::

	        {
	            "weighting": "Hours (tank estimate)" | "Hours × Rate (tank estimate)",
	            "rows": [
	                {
	                    "equipment": str,
	                    "hours": float,
	                    "rate_used": float,
	                    "allocated_litres": float,
	                    "review_flag": 0 | 1,
	                    "remainder": 0 | 1,
	                },
	                ...,
	            ],
	            "review_reason": str | None,  # set when no row is written
	        }
	"""
	total_litres = flt(fill.litres)
	if total_litres <= 0:
		return {"weighting": _weighting_of_company(fill.company), "rows": [], "review_reason": "zero litres"}
	month, year = _month_year(fill.date)
	hours_map = project_operating_hours(fill.project, month, year, fill.company) if fill.project else {}
	weighting = _weighting_of_company(fill.company)
	universe = _universe(fill, hours_map)
	if not universe:
		return {
			"weighting": weighting,
			"rows": [],
			"review_reason": "no equipment with cards or matched rows",
		}
	rates_map = (
		_row_rates(universe, fill.date) if weighting == HOURS_RATE_WEIGHTING else dict.fromkeys(universe, 0.0)
	)
	weights = _weights(universe, hours_map, rates_map, weighting)
	if not weights:
		reason = "no operating hours" if weighting == HOURS_WEIGHTING else "no hours or rate"
		return {"weighting": weighting, "rows": [], "review_reason": reason}
	shares = split_by_weights(total_litres, weights, LITRES_PRECISION)
	# the drift in split_by_weights lands on the key with the biggest share (sorted key tiebreak)
	remainder_key = max(sorted(shares), key=lambda k: shares[k]) if shares else None
	rows: list[dict] = []
	for name in universe:
		hours = flt(hours_map.get(name) or 0)
		rate = flt(rates_map.get(name) or 0) if weighting == HOURS_RATE_WEIGHTING else 0.0
		share = flt(shares.get(name) or 0, LITRES_PRECISION)
		needs_review = int(name not in weights)
		rows.append(
			{
				"equipment": name,
				"hours": hours,
				"rate_used": rate,
				"allocated_litres": 0.0 if needs_review else share,
				"review_flag": needs_review,
				"remainder": int(name == remainder_key and not needs_review),
			}
		)
	return {"weighting": weighting, "rows": rows, "review_reason": None}


def write_rows(fill) -> None:
	"""Write the Diesel Fill Allocation rows and the parent's ``allocation_review`` field. Called
	from ``ProjectDieselFill.before_submit`` for a tank-style fill with no existing rows. The
	rows are appended with ``basis = estimated`` (G1 scope: no manual overrides, G2 adds them).
	A fill with ``card_equipment`` set (one measured equipment) is NOT processed here.
	"""
	if fill.get("card_equipment"):
		# measured fill: FR-033 and existing diesel.py handle it; no allocation rows
		fill.set(TABLE, [])
		fill.set("allocation_review", None)
		return
	if fill.get(TABLE):
		# a submitted fill never reaches here (before_submit on a brand-new submit); belt-and-braces
		return
	plan = plan_allocation(fill)
	fill.set(TABLE, [])
	fill.set("allocation_review", None)
	if not plan["rows"]:
		fill.set("allocation_review", plan.get("review_reason") or None)
		return
	frozen_on = now_datetime().replace(microsecond=0)
	rule = _rule_tag(plan["weighting"])
	for row in plan["rows"]:
		fill.append(
			TABLE,
			{
				"equipment": row["equipment"],
				"basis": BASIS_ESTIMATED,
				"rule": rule,
				"hours": row["hours"],
				"rate_used": row["rate_used"],
				"allocated_litres": row["allocated_litres"],
				"remainder": row["remainder"],
				"review_flag": row["review_flag"],
				"frozen_on": frozen_on,
			},
		)
