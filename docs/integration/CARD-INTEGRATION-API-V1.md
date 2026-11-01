# CARD integration API v1 (CARD 4.4.0)

For apps that show equipment screens (DAWM field and mobile apps) and must use CARD as the one equipment
application instead of equipment_manager. ERPNext stays the source of Assets, stock and accounting.
Module: `card.integration_v1` (call it in-process from Python, or over REST as `/api/method/card.integration_v1.<fn>`).
Every call runs with the caller's own permissions; nothing is written for a GET.

## Registering a field app (hooks of the calling app)

```python
# hooks.py of the calling app (example): every source DocType names its authorizer
card_field_meter_sources = {
	"Dawm Equipment Operation Log": "dawm.integrations.card.operation_log_concerns_equipment",
	"Dawm Diesel Receipt": "dawm.integrations.card.receipt_concerns_equipment",
}
```

`fn(source_doc, equipment) -> bool` must prove that the document is about that equipment (for example the
operator's assigned unit). A source without an authorizer is refused (fail closed).

## Calls

| Function | Method | Arguments | Returns |
|---|---|---|---|
| `api_version` | GET | — | `{"version": "1.0"}` |
| `equipment_for_asset` | GET | `asset` | Card Equipment name or `None` (also when not readable) |
| `equipment_for_assets` | GET | `assets` (list or JSON) | `{asset: equipment}` for readable ones |
| `equipment_snapshot` | GET | `equipment` | name, equipment_name, company, asset, current_project, status, meter_type, current_meter, last_service_meter, last_service_date, maintenance_status, next_service_meter, hours_since_last_service, last_fuelling {reading_time, reading, litres, source_type}, service_lines [{service_name, interval_hours, last_meter, last_date, next_at, remaining, status}] |
| `record_meter_reading` | POST | `equipment, reading, source_doctype, source_name, reading_time=None, source_key=None, strict=0` | the Card Meter Reading (source type "Field Operation") |
| `record_machine_fuelling` | POST | `equipment, litres, reading, source_doctype, source_name, reading_time=None, source_key=None, strict=0` | the Card Meter Reading (source type "Field Fuelling"); **no cost is posted** |
| `reject_source_readings` | POST | `source_doctype, source_name, reason=None` | names of the readings of that document (now Rejected) |

Rules of the field readings:
- The caller needs **write** on the source document; the source DocType must be registered with an authorizer; the
  equipment's company must be permitted to the caller; every registered authorizer must agree. Requests on one
  source document are serialized.
- One reading per (source document, `source_key`) — without a key, one per source document (send `start` / `end`
  keys for a shift): the same value again returns the same reading; a new value rejects the old one (kept, with the
  reason) and records the new one; a replaced reading cannot be made Valid again.
- `reject_source_readings` on a live source checks the authorizer for each reading's equipment; for a deleted source
  only a System Manager may call it.
- `strict=1` refuses a reading lower than the last valid reading of the equipment; without it the reading is kept
  as Suspect. Implausible jumps are always Suspect, future times are refused.

## Maintenance (Desk / REST, `card.maintenance`)

| Function | Method | Purpose |
|---|---|---|
| `approve_order(order)` | POST | Due → Approved (Card Manager / System Manager) |
| `start_order(order)` | POST | Approved → In Progress |
| submit the order | — | Completed: writes the meter reading, moves the last service of the covered service lines |
| `make_material_request(order)` | POST | draft Material Request (Material Issue) |
| `make_stock_entry(order)` | POST | draft Stock Entry (Material Issue) from the order's warehouse |
| `make_purchase_invoice(order)` | POST | draft Purchase Invoice from the order's supplier |
| `get_plan_kit(equipment)` | GET | kit lines of the active plan |

Card Settings (level 2): `auto_create_due_orders` (off) creates one draft **Due** order when a machine becomes due;
while it is on, every new Scheduled Service order starts as **Due** and needs a Card Manager of its company to
approve it. `warranty_alert_days` (30) for the daily part-warranty alert (also parts already past their warranty).
An order's parts are issued one way only: Material Request or Stock Entry.
