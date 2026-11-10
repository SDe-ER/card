---
title: Equipment API
description: Endpoints for units and components, creating equipment from an ERPNext Asset, the operating heatmap and unit integrity checks.
sidebar:
  order: 2
---

## Overview

These endpoints back the **Card Equipment** form: the unit component changes, the prefill from an ERPNext Asset, the
per-shift heatmap and the unit integrity check. Plain equipment records are read and written with the standard
resource API (`/api/resource/Card Equipment`). See the [API overview](/card/api-reference/overview/) for
authentication and errors.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `card.api.get_asset_prefill` | Values the equipment form takes from a submitted Asset. |
| POST | `card.api.create_equipment_from_asset` | Create (or prefill) a Card Equipment from a submitted Asset. |
| GET | `card.api.available_assets_query` | Link query: submitted Assets not yet linked to equipment. |
| GET | `card.api.get_only_company` | The company a new CARD form takes when the user sees exactly one. |
| GET | `card.card.doctype.card_equipment.card_equipment.get_shift_heatmap` | Daily operating hours per shift. |
| GET | `card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues` | Records that break the unit rules. |
| POST | `card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag` | Reset one piece's unit-component flag. |
| POST | `card.card.doctype.card_equipment.card_equipment.replace_component` | Replace a component of a unit from a date. |
| POST | `card.card.doctype.card_equipment.card_equipment.move_component` | Move a component to another unit from a date. |

## get_asset_prefill

`GET /api/method/card.api.get_asset_prefill`

Returns the Card Equipment values the form fills from a submitted ERPNext Asset. Read only.

**Permission:** read on Card Equipment and read on the Asset.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `asset` | string | Yes | Name of a submitted Asset. |

**Returns:** an object with the equipment fields taken from the Asset — `company`, `image`, `cost_center`, `operator`
(custodian), `insurance_company`, `insurance_policy_no`, `insurance_expiry`, `equipment_name`, `brand` (from the Asset
item), `equipment_type` (mapped from the Asset category) — and `equipment_type_from_asset` (1 or 0). Only the fields
the user may read on Card Equipment are returned (for example no cost center without the right permission level).

```bash
curl -s -G "https://<your-site>/api/method/card.api.get_asset_prefill" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "asset=<asset-name>"
```

## create_equipment_from_asset

`POST /api/method/card.api.create_equipment_from_asset`

Builds a Card Equipment from a submitted Asset with minimum input. With `save` and nothing left to ask, the equipment
is created with the user's own permissions and full validation; otherwise nothing is inserted and the prefilled values
are returned with the fields still missing.

**Permission:** create on Card Equipment and read on the Asset.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `asset` | string | Yes | Submitted Asset to link. |
| `ownership` | string | No | «ملك» (Owned, default) or «طرف ثالث» (Third party). Rented equipment never gets an Asset and is refused. |
| `save` | int | No | `1` to create at once when possible; default `0`. |

**Returns:** `{"name": "<equipment>"}` when created; otherwise the readable prefilled fields plus `missing` — a list
of `equipment_type`, `daily_hours` and, for third-party equipment, `rental_direction`.

**Side effects:** with `save=1`, inserts a Card Equipment linked to the Asset. Owned equipment gets the company as
operator and fuel party; the daily hours default to the Card Settings value. An Asset already linked to equipment is
refused; two simultaneous creations of the same Asset are serialised by a row lock.

```bash
curl -s -X POST "https://<your-site>/api/method/card.api.create_equipment_from_asset" \
  -H "Authorization: token <api_key>:<api_secret>" \
  -H "Content-Type: application/json" \
  -d '{"asset": "<asset-name>", "ownership": "ملك", "save": 1}'
```

## available_assets_query

`GET /api/method/card.api.available_assets_query`

Link-field search for the equipment's Asset field: submitted Assets of the given company that are not Scrapped or Sold
and not already linked to a Card Equipment.

**Permission:** a role that may create or write Card Equipment, and read (not only select) on Asset; companies limited
to those the user may see for Card Equipment.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `doctype` | string | Yes | Standard link-query argument (`Asset`). |
| `txt` | string | Yes | Search text (name or Asset name). |
| `searchfield` | string | Yes | Standard link-query argument. |
| `start` | int | Yes | Offset. |
| `page_len` | int | Yes | Page size (0 means 20). |
| `filters` | object | Yes | `{"company": "<company>"}`, optional company. |

**Returns:** a list of `[name, asset_name]` pairs.

```bash
curl -s -G "https://<your-site>/api/method/card.api.available_assets_query" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "doctype=Asset" --data-urlencode "txt=" --data-urlencode "searchfield=name" \
  --data-urlencode "start=0" --data-urlencode "page_len=20" \
  --data-urlencode 'filters={"company":"Example Contracting Co."}'
```

## get_only_company

`GET /api/method/card.api.get_only_company`

The company a new CARD form fills in when the user may list exactly one company; otherwise `null`. The field stays
editable.

**Permission:** any logged-in user; returns `null` without read or select on Company.

**Parameters:** none. **Returns:** a company name or `null`.

```bash
curl -s "https://<your-site>/api/method/card.api.get_only_company" \
  -H "Authorization: token <api_key>:<api_secret>"
```

## get_shift_heatmap

`GET /api/method/card.card.doctype.card_equipment.card_equipment.get_shift_heatmap`

Daily operating hours of one machine from its submitted monthly cards, split by shift, for the two heatmaps on the
equipment form. Days with zero hours are left out.

**Permission:** read on the equipment and read on Card Monthly Card.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Card Equipment name. |

**Returns:** `{"day": {<unix timestamp>: hours}, "night": {<unix timestamp>: hours}, "has_night": true|false}`.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.get_shift_heatmap" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "name=EQ-0001"
```

## get_unit_integrity_issues

`GET /api/method/card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues`

Existing records that break the owned-only unit rule, or whose unit-component flag does not match the component
tables, among the equipment the user may read. Read only.

**Permission:** read on Card Equipment (Company User Permissions apply).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `company` | string | No | Limit to one company. |

**Returns:** a list of `{issue, message, equipment, company, unit}`. Issues: "Unit is not owned", "Component is not
owned", "Component flag without a unit", "Component flag after leaving its unit", "Current component without the
flag".

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "company=Example Contracting Co."
```

## resync_unit_component_flag

`POST /api/method/card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag`

Sets one machine's unit-component flag to the value its component rows give.

**Permission:** write on the equipment and write access to the permission level of the flag (Card Manager level).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `equipment` | string | Yes | Card Equipment name. |

**Returns:** the derived flag, `1` or `0`. **Side effects:** stores the flag; a change leaves a comment on the piece.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"equipment": "EQ-0002"}'
```

## replace_component

`POST /api/method/card.card.doctype.card_equipment.card_equipment.replace_component`

From `date`, `new_component` takes the place of `component` in `unit`. The unit stays one equipment on its monthly card;
only the dated history of its pieces changes.

**Permission:** write on the unit and write access to its components table (Card Manager level); read on the new
component.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `unit` | string | Yes | The unit (Card Equipment with "is unit"). |
| `component` | string | Yes | The current component to close. |
| `new_component` | string | Yes | The component that replaces it. |
| `date` | date | Yes | First day of the new component; must be after the current row's start. |
| `reason` | string | No | Change reason stored on both rows. |

**Returns:** the unit name. **Side effects:** closes the current row the day before `date` and adds a new row. Refused
when a submitted card of the unit ends on or after `date`, or when the new component is not on the unit's project that
day.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.replace_component" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"unit": "EQ-0001", "component": "EQ-0002", "new_component": "EQ-0003", "date": "2026-02-01", "reason": "Engine swap"}'
```

## move_component

`POST /api/method/card.card.doctype.card_equipment.card_equipment.move_component`

From `date`, `component` leaves `unit` and works in `target_unit` on the same project.

**Permission:** component write access (Card Manager level) on both units.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `unit` | string | Yes | Current unit. |
| `component` | string | Yes | Component to move. |
| `target_unit` | string | Yes | Another unit. |
| `date` | date | Yes | First day in the target unit. |
| `reason` | string | No | Change reason. |

**Returns:** the target unit name. **Side effects:** closes the row in the source unit, adds it to the target unit and
syncs the component flags once. Refused when either unit has a submitted card covering `date` or later, or the
component is not on the target's project that day.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.move_component" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"unit": "EQ-0001", "component": "EQ-0002", "target_unit": "EQ-0004", "date": "2026-02-01"}'
```

## Related

- [Equipment](/card/features/equipment/)
- [Units and components](/card/features/units-components/)
- [Maintenance and asset reports](/card/reports/maintenance-assets/)
