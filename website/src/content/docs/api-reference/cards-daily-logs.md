---
title: Cards and Daily Logs API
description: Endpoints for the monthly card form, generating draft cards from daily logs, cancelling with a reason, and the workspace number cards and chart.
sidebar:
  order: 3
---

## Overview

Monthly cards and daily logs are read and written with the standard resource API (`/api/resource/Card Monthly Card`,
`/api/resource/Card Daily Log`); every rule runs on save, submit and cancel whatever the route. The endpoints below
add what the forms and the workspace need: the card context, the generation of draft cards from approved daily logs,
the cancel-with-reason action and the dashboard figures.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `card.card.doctype.card_monthly_card.card_monthly_card.get_card_context` | Projects and days of a machine in a month. |
| POST | `card.daily_log_generation.generate_monthly_cards` | Create or update draft cards from approved daily logs. |
| POST | `card.cancel_reason.cancel_with_reason` | Cancel a CARD transaction and store the reason. |
| POST | `card.card_value.supplier_cost_last_month` | Number card: supplier rental cost of last month. |
| POST | `card.card_value.customer_value_last_month` | Number card: customer operating value of last month. |
| POST | `card.card_value.internal_value_last_month` | Number card: internal operating value of last month. |
| POST | `card.card_value.cards_without_internal_rate_last_month` | Number card: cards of owned equipment without an internal rate. |
| POST | `card.card_value.hours_without_internal_rate_last_month` | Number card: hours of those cards. |
| POST | `card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get` | Chart source "Card Monthly Values". |

## get_card_context

`GET /api/method/card.card.doctype.card_monthly_card.card_monthly_card.get_card_context`

What the card form fills in once the equipment, month and year are chosen: the projects the approved transports put the
machine on that month, and the days it was on the chosen (or only) project. For a unit, a day counts only when every
piece in the unit was on the project; a piece's days inside a unit period are not offered. Read only.

**Permission:** read on the equipment.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `equipment` | string | Yes | Card Equipment name. |
| `month` | string | Yes | Month number, for example `01`. |
| `year` | string | Yes | Year, for example `2026`. |
| `project` | string | No | Project; when empty and only one project exists, that one is used. |

**Returns:** `{"projects": [...], "project": "<project or null>", "days": ["2026-01-01", ...]}`.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.card_monthly_card.card_monthly_card.get_card_context" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "equipment=EQ-0001" --data-urlencode "month=01" --data-urlencode "year=2026"
```

## generate_monthly_cards

`POST /api/method/card.daily_log_generation.generate_monthly_cards`

Creates or updates the **draft** day-shift and night-shift monthly cards of one company, project and month (optionally
one machine) from the **Approved** daily logs. It never submits a card and never changes a submitted one.

**Permission:** create on Card Monthly Card for that company and project, and read on Card Daily Log; with
`equipment`, read on that equipment, which must belong to the company. The project must belong to the company.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `company` | string | Yes | Company. |
| `project` | string | Yes | Project of the company. |
| `month` | string | Yes | `YYYY-MM`, or any date of the month. |
| `equipment` | string | No | Limit to one machine. |

**Returns:** an object of lists: `created`, `updated`, `unchanged`, `kept_submitted`, `overwritten_days`,
`cleared_days`, `skipped_days`, `conflicts` (a machine changed by another run at the same time — run again) and
`errors` (per machine and shift, with the validation message; other machines continue).

**Side effects:** inserts or saves draft monthly cards. Runs for the same machine are serialised with a row lock.

```bash
curl -s -X POST "https://<your-site>/api/method/card.daily_log_generation.generate_monthly_cards" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"company": "Example Contracting Co.", "project": "PROJ-0001", "month": "2026-01"}'
```

## cancel_with_reason

`POST /api/method/card.cancel_reason.cancel_with_reason`

The form's **Cancel**: stores the cancel reason and cancels the stored document in one request. A refused cancel rolls
the reason back with it. The reason is stored as plain text.

**Permission:** Frappe's cancel permission on the document and the DocType's company isolation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `doctype` | string | Yes | `Card Monthly Card`, `Equipment Transport` or `Project Diesel Fill`; any other is refused. |
| `name` | string | Yes | Document name. |
| `reason` | string | No | Cancel reason (the DocType's own rules decide whether it is required). |

**Returns:** `{"name": "<name>", "docstatus": 2}`. **Side effects:** sets `cancel_reason` and cancels the document.

```bash
curl -s -X POST "https://<your-site>/api/method/card.cancel_reason.cancel_with_reason" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"doctype": "Card Monthly Card", "name": "<card-name>", "reason": "Wrong project"}'
```

## Number cards of last month

The five `card.card_value.*_last_month` functions feed the workspace **Number Cards**. Frappe's number card widget
always calls with `POST`, so these side-effect-free reads accept `POST` only. They total the monthly cards whose period
starts in the previous calendar month.

**Permission:** read on Card Monthly Card (only cards the user may read count). Internal values need read access to the
internal rate fields of Card Equipment; without it the internal figures are `null`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `filters` | object | No | `{"company": "<company>", "include_drafts": 0}`; `include_drafts` is `0` or `1`. |

**Returns:** `{"value": <number or null>, "fieldtype": "Currency"|"Int"|"Float", "route": ["List", "Card Monthly Card"],
"route_options": {...}}` — the route opens the card list behind the figure.

| Function | Value |
|---|---|
| `supplier_cost_last_month` | Supplier rental cost (Currency). |
| `customer_value_last_month` | Customer operating value (Currency). |
| `internal_value_last_month` | Internal operating value of owned equipment (Currency). |
| `cards_without_internal_rate_last_month` | Cards whose equipment has no internal rate (Int). |
| `hours_without_internal_rate_last_month` | Hours of those cards (Float). |

```bash
curl -s -X POST "https://<your-site>/api/method/card.card_value.supplier_cost_last_month" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"filters": {"company": "Example Contracting Co."}}'
```

## Card Monthly Values chart source

`POST /api/method/card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get`

The value of every monthly card per period in three series: supplier rental cost, customer operating value and
internal operating value. Read only; not cached, so one user's totals are never served to another company.

**Permission:** read on the Dashboard Chart (when `chart_name` is given) and read on Card Monthly Card.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `chart_name` | string | No | A Dashboard Chart record using this source. |
| `chart` | object | No | Chart settings when no `chart_name` is given. |
| `filters` | object | No | `{"company": ..., "include_drafts": ...}`; defaults to the chart's filters. |
| `from_date`, `to_date` | date | No | For the "Select Date Range" timespan. |
| `timespan` | string | No | Default from the chart, else "Last Year". |
| `time_interval` | string | No | Default from the chart, else "Monthly". |
| `no_cache`, `heatmap_year`, `refresh` | — | No | Accepted for compatibility with the chart widget; not used. |

**Returns:** `{"labels": [...], "datasets": [{"name": "<series label>", "values": [...]}, ...]}`. The internal series is
included only for users who may read the internal rate fields of Card Equipment.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"chart": {"timespan": "Last Year", "time_interval": "Monthly"}, "filters": {"company": "Example Contracting Co."}}'
```

## Related

- [Monthly cards](/card/features/monthly-cards/)
- [Daily logs](/card/features/daily-logs/)
- [Workspace and dashboard](/card/features/workspace-dashboard/)
