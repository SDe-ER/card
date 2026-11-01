# equipment_manager (legacy) — what it was and where it went in CARD

Record of the separate `equipment_manager` app (repository `SDe-ER/equipment_manager`, `main` 3fb3af5, version
0.0.2) so that nothing it did is lost when it is retired. Source: the repository code; production facts are in the
consolidation audit evidence, not here (this file holds no site data).

## What the app contained

| Part | Type | What it did | Where it is in CARD |
|---|---|---|---|
| Fueling Log | Submittable DocType (`FLG-.YYYY.-.MM.-.DD.-.{asset}.-.####`) | One diesel fill of one Asset: litres, price, transport fee, hour meter, previous meter, hours run, litres per hour, odometer, driver, maintenance status of that fill, link to a Maintenance Request | Per-machine litres and meter in the CARD diesel fill (FR-099); each fill writes a Card Meter Reading. Old rows: Legacy Fueling Log readings with all original values in `legacy_values` (FR-101). Cost stays with the CARD diesel fill and supplier invoices (FR-033) |
| Maintenance Request | Submittable DocType | Request for a service at a due meter, with required parts | Card Maintenance Order (FR-100) |
| Maintenance Request For Asset | Submittable DocType | Filter-by-filter request per Asset (oil, diesel, water separator, air, other parts) with a Purchase Invoice link | Card Maintenance Order with items from the plan kit; Purchase Invoice created as a draft by ERPNext rules |
| Equipment Maintenance Settings | Submittable DocType per Asset | Filter and spare-part lists per Asset | Card Maintenance Plan (per machine or per model) with a kit |
| Equipment Spare Part, Maintenance Required Item | Child tables | Part lines | Card Maintenance Kit Item, Card Maintenance Order Item |
| Diesel Consumption and Cost Analysis | Script Report | Litres and cost per Asset | Equipment Fuel Consumption (litres per metered hour); cost: existing CARD diesel reports |
| صيانه مطلوبة | Dashboard Chart | Count of due maintenance | Equipment Maintenance Status report (filter "Only due and due soon") |
| Asset custom fields (`custom_current_operating_hours`, `custom_hours_since_last_service`, `custom_total_diesel_consumed`, `custom_last_fueling_hour_meter`) | Fixtures + `asset_schema.py` projection | Running totals on the Asset | Card Equipment `current_meter`, `last_service_meter`, `maintenance_status`, `next_service_meter`; CARD never writes the Asset (FR-098) |
| Site Server/Client Scripts (outside the repository) | Site configuration | 300 h maintenance rule per fill, client-side Purchase Invoice with a fixed account | Replaced by FR-100 server logic; the scripts are archived by `archive()` and disabled only with an Owner GO |

Roles used by the old app: System Manager, Maintenance Manager, Maintenance User. CARD uses its own roles
(System Manager, Card Manager, Card User, Card Supervisor, Accounts Manager).

## Retirement tools (FR-101, System Manager only)

1. `card.legacy_equipment_manager.archive` (POST): one private JSON file on Card Settings with every record, child
   row, the related site scripts and the Asset fields; its SHA-256 is written in a Comment.
2. `card.legacy_equipment_manager.import_fueling_logs` with `dry_run=1` first, then `dry_run=0`: idempotent.
3. `card.legacy_equipment_manager.verify` (GET): must return `ok: true` before any removal.

Uninstalling the app is a bench action by the owner after a separate approval; CARD never uninstalls it. Other apps
that use it (DAWM Equipment Ops) must be checked first — see the consolidation retirement plan.
