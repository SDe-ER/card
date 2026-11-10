# CARD settings and hardcoded constants — inventory

**Status: inventory (documentation only).** Issue #50, work package WP-18. Nothing in this file changes code or
data. It lists every setting CARD reads, every default the code falls back to, and every hardcoded constant that
affects behaviour, so that a later change can move a value to the right setting without guessing.

- Generated from `main` @ `1b7c20d` (v4.5.0) by reading `card/settings.py`, the Card Settings and Card Company
  Settings DocType JSON, and a grep of `card/` (tests and patches excluded) for every field name and every
  module-level constant. Line numbers are those of that commit; re-grep before you rely on one.
- "Target" says where the value should be configured if it is ever made configurable. It is a proposal, not a
  decision. Changing any value needs its own task, CHANGELOG entry and owner approval.

## 1. Precedence

CARD resolves a value in this order. The first level that has a value wins.

| Level | Where | Scope | Examples |
|---|---|---|---|
| 1. Document | The record itself (Card Equipment, Card Monthly Card, Project Diesel Fill, Equipment Transport, Card Equipment Assignment) | One record | Equipment rate and rate basis, card shift, a fill's price exception, an assignment's cost center |
| 2. Card Company Settings | Child table `company_settings` of Card Settings, one row per company | One company | Accounts, cost center, tax templates, posting items, diesel price, VAT basis |
| 3. Card Settings | Single DocType `Card Settings` | The site | Shift limits, standard month hours, period lock, roles, warehouses |
| 4. Code default | `card/settings.py` `_DEFAULTS` (lines 11-47) or an inline fallback | Built in | 12 h shift limit, 260 h month, tolerance 0.01 |

Notes on how the levels behave today:

- A document value is taken first only where the code reads it first. Some Card Settings values are only
  **pre-fills for new records** (`card_equipment.py:394-414` `apply_new_record_defaults`): a saved record never
  changes when the setting changes.
- `card.settings.setting()` (`settings.py:50-66`) reads the raw `tabSingles` row. A field that was never saved, or is
  saved empty, returns the code default. A numeric default makes the stored value a float.
- Several call sites add a second inline fallback (`or 260`, `or 12`, `or 0.01`, `or "Card Manager"`). Those
  fallbacks also apply when the setting is saved as `0` or empty, so `0` cannot switch them off.
- Submitted monthly cards keep a snapshot of the values they used (`card_monthly_card.py:503-525`
  `_snapshot_settings_used`: `daily_hours_used`, `hourly_rate_used`, `diesel_policy_used`, `customer_rate_used`,
  `direction_used`, `customer_used`, `rate_basis_used`). Diesel fills keep their price (FR-002). No other setting is
  dated or snapshotted (#50 "effective dates": missing).

## 2. Card Settings (single DocType)

Source: `card/card/doctype/card_settings/card_settings.json`. Field level is the DocType permlevel. "Code default"
is `settings.py` `_DEFAULTS`.

| Field | Type | JSON default | Code default | Read by (file:line) | Status |
|---|---|---|---|---|---|
| `enable_accounting` | Check, level 2 | 0 | 0 | `gl/preflight.py:18`; `accounting_settings.py:15` (direct `get_single_value`) | Used. Two readers; the docstring of `accounting_settings.py` still says "none yet" |
| `auto_submit` | Check, level 2 | 0 | — (removed from `_DEFAULTS`, FR-124) | none (only the one-time patch `v1_2/init_card_settings_defaults.py:16`, which wrote the stored default) | **Deprecated** (FR-124, in review): hidden, read only, "Deprecated – not used"; column and value kept |
| `default_shift` | Select, level 2 | نهاري | نهاري | `card_monthly_card.py:87` | Used: pre-fill of a new card's shift |
| `max_day_shift_hours` | Float, level 2 | 12 | 12.0 | `card_monthly_card.py:180-181` (inline `or 12`) | Used: warning only (FR-017) |
| `max_night_shift_hours` | Float, level 2 | 12 | 12.0 | `card_monthly_card.py:180-181` (inline `or 12`) | Used: warning only (FR-017) |
| `default_daily_hours` | Float, level 2 | 0 | 0.0 | `card_equipment.py:398`; `api.py:391-392` | Used: pre-fill of new equipment |
| `default_fuel_charged_to` | Select, level 2 | — | "" | `card_equipment.py:401` | Used: pre-fill |
| `default_operator_on` | Select, level 2 | — | "" | `card_equipment.py:404` | Used: pre-fill |
| `reconciliation_tolerance` | Currency, level 2 | 0.01 | 0.01 | `gl/posting.py:87`, `gl/events.py:234`, `gl/journal_link.py:106`, `gl/integrity.py:572,653`, `equipment_customer_statement.py:421` (each with inline `or 0.01`) | Used |
| `warn_on_shift_hours_exceeded` | Check, level 2 | 1 | 1 | `card_monthly_card.py:340` | Used |
| `warn_outside_rental_period` | Check, level 2 | 1 | 1 | `card_monthly_card.py:366` | Used |
| `default_statement_type` | Select, level 2 | مورد | مورد | `equipment_supplier_statement.py:22`, `.js:145-146`; `api.py:292` | Used: report filter default |
| `include_draft_in_reports` | Check, level 2 | 0 | 0 | `equipment_supplier_statement.py:42`, `statement_pdf.py:97`, `equipment_customer_statement.py:44`, both `.js`; `api.py:293` | Used |
| `period_lock_date` | Date, level 2 | — | None | `period_lock.py:40`; `gl/preflight.py:123` | Used (FR-050) |
| `period_lock_override_role` | Link Role, level 2 | — | None | `period_lock.py:47`; `gl/preflight.py:125` | Used |
| `notify_on_card_submit` | Check, level 2 | 0 | 0 | `card_monthly_card.py:490` | Used |
| `notify_on_posting` | Check, level 2 | 0 | — (removed from `_DEFAULTS`, FR-124) | none (only the one-time patch `v1_2/init_card_settings_defaults.py:27`, which wrote the stored default) | **Deprecated** (FR-124, in review): hidden, read only, "Deprecated – not used"; column and value kept |
| `notify_on_period_lock_override` | Check, level 2 | 0 | 0 | `period_lock.py:72` | Used |
| `default_rate_basis` | Select, level 2 | — | "" | `card_equipment.py:408` | Used: pre-fill of both rate bases |
| `standard_month_hours` | Float, level 2 | 260 | 260.0 | `card_equipment.py:152`, `card_monthly_card.py:437` (inline `or 260`) | Used (FR-016) |
| `sync_equipment_location_daily` | Check, level 2 | 0 | 0 | `transfer.py:222` (scheduler `hooks.py:225-228`) | Used: off by default (#56) |
| `diesel_supplier_policy` | Select, level 2 | متغير | متغير | `project_diesel_fill.py:20,850` (inline `or "متغير"`); `card_settings.py:39` | Used |
| `diesel_supplier` | Link Supplier, level 2 | — | "" | `project_diesel_fill.py:18` | Used |
| `diesel_supplier_editor_role` | Link Role, level 2 | Card Manager | Card Manager | `project_diesel_fill.py:22,857` (inline `or "Card Manager"`) | Used |
| `diesel_price_exception_role` | Link Role, level 2 | Accounts Manager | Accounts Manager | `project_diesel_fill.py:196,216,232,239,263,320` | Used (FR-002) |
| `diesel_zero_price_role` | Link Role, level 2 | — | None | `project_diesel_fill.py:200` | Used: empty = nobody may save a zero price |
| `transport_price_editor_role` | Link Role, level 2 | Card Manager | Card Manager | `equipment_transport.py:418` (inline `or "Card Manager"`) | Used |
| `project_transport_prices` | Table Card Project Transport Price, level 2 | — | — | `equipment_transport.py:395` (via the child DocType); `card_settings.py:43` | Used |
| `adjustment_types` | Table Card Adjustment Type | — | — | `gl/masters.py:196`, `gl/posting.py:81`, `gl/preflight.py:202`, `card_monthly_card.py:238` | Used (per company) |
| `location_cost_centers` | Table Card Location Cost Center, level 2 | — | — | `gl/posting.py:323`, `equipment_transport.py:275` (via the child DocType) | Used (FR-091, FR-093) |
| `default_store_warehouse` | Link Warehouse | — | "" | `materials.py:234`; `tool_custody.py:69,420` | Used |
| `tool_custody_warehouse` | Link Warehouse | — | "" | `employee_tool_custody.py:57,237,277`; `materials.py:314` | Used |
| `repeat_request_days` | Int | 30 | 30 | `materials.py:120` (inline `or 30`) | Used |

`default_store_warehouse`, `tool_custody_warehouse` and `repeat_request_days` are the site-wide fallback. FR-135 (in
review) adds the per-company values on Card Company Settings (`store_warehouse`, `custody_warehouse`,
`repeat_request_days`); an empty company value uses these.

## 3. Card Company Settings (one row per company)

Source: `card/card/doctype/card_company_settings/card_company_settings.json`. All fields are permlevel 1. The row
is read by `gl/preflight.py:36-41` `company_settings_row` (posting) and `accounting_settings.py:20-40`
`get_company_settings` (diesel price, reports).

| Field | Type | Read by | Status |
|---|---|---|---|
| `company` | Link Company | every reader (row key; duplicates refused, `card_settings.py:18-23`) | Used |
| `equipment_rental_expense_account`, `diesel_expense_account`, `transport_expense_account` | Link Account | `gl/posting.py`; `equipment_expenses_without_equipment.py` | Used |
| `equipment_rental_income_account`, `payable_account`, `receivable_account` | Link Account | `gl/posting.py` | Used |
| `cost_center` | Link Cost Center | `gl/posting.py:791` (`line.get("cost_center") or row.cost_center`) | Used as a last fallback on an invoice line. FR-091 says project work never takes the company default; the allocation refuses a build first in the cases it covers. Re-check this fallback in the next posting review |
| `purchase_tax_template`, `sales_tax_template` | Link tax template | `gl/masters.py`, `gl/posting.py`, `gl/preflight.py`, `gl/integrity.py` | Used |
| `rental_item`, `diesel_item`, `transport_item`, `rental_out_item` | Link Item | `gl/masters.py:15-20` (created when empty), `gl/posting.py`, `gl/preflight.py` | Used |
| `vat_item_tax_template`, `vat_zero_item_tax_template` | Link Item Tax Template | `gl/masters.py:182-194` (created when empty), `gl/posting.py`, `gl/preflight.py` | Used |
| `diesel_unit_price` | Currency | `project_diesel_fill.py:177-186` `diesel_price`; `card_settings.js` | Used (FR-002). One value, no dates (FR-035 planned) |
| `diesel_price_vat_basis` | Select (empty / Exclusive / Inclusive) | `gl/posting.py:925`; `gl/integrity.py:440` | Used (FR-090). Empty = posting refused for review |
| `equipment_status_rule` | Select ("Warn only (equipment status)" / "Refuse (equipment status)"; empty = Warn only) | `card/equipment_status.py` `status_rule`, `check_equipment_status` (Card Equipment Assignment, Equipment Transport, Card Monthly Card) | Used (FR-122, In review). Default Warn only |
| `store_warehouse`, `custody_warehouse` | Link Warehouse | `card/settings.py` `store_warehouse`, `custody_warehouse` (materials, Employee Tool Custody, Tool Custody screen) | Used (FR-135, In review). Empty = the Card Settings value; must belong to the row's company (save and read time) |
| `repeat_request_days` | Int | `card/settings.py` `repeat_request_days` (`materials.repeat_days`) | Used (FR-135, In review). Empty or 0 = the Card Settings value (30 by default) |
| `bank_cash_account` | Link Account | none (only the generic account-company check in `card_settings.py` `validate`, which covers every Account link of a row) | **Deprecated** (FR-124, in review): hidden, read only, "Deprecated – not used"; column and value kept |
| `mode_of_payment` | Link Mode of Payment | none | **Deprecated** (FR-124, in review): hidden, read only, "Deprecated – not used"; column and value kept |

## 4. Dead settings (FR-015)

The four settings below exist in the DocTypes, are written by patch `v1_2/init_card_settings_defaults.py` and (for
the first two) appear in `settings.py` `_DEFAULTS`, but no code reads them. Changing them has no effect.

| Setting | DocType | Real status on `main` | Options (owner decision FR-015, WP-08) |
|---|---|---|---|
| `auto_submit` | Card Settings | No reader. Monthly postings are always drafts (FR-004) | Hide with a deprecation note, or implement auto-submit of postings (accounting impact) |
| `notify_on_posting` | Card Settings | No reader. No caller of `notifications.notify` passes this flag | Hide, or add a notification in `gl/posting.py` |
| `bank_cash_account` | Card Company Settings | No reader. CARD creates no Payment Entry (FR-012 removed) | Hide until a payment design exists |
| `mode_of_payment` | Card Company Settings | No reader | Same as `bank_cash_account` |

No field is deleted without the owner's approval (FEATURE-REGISTRY rules).

**FR-124 (WP-08, issue #50, in review): all four are retired, not deleted.** Each field is `hidden: 1` and
`read_only: 1` with the description "Deprecated – not used" (Arabic in `card/locale/ar.po`: "متوقف – غير مستخدم").
The columns and any stored values stay; no patch is needed (hiding is a DocType property). `auto_submit` and
`notify_on_posting` are removed from `settings.py` `_DEFAULTS` (no reader). The one-time patch
`v1_2/init_card_settings_defaults.py` is unchanged (it has already run and only wrote the stored defaults).
`card/tests/test_deprecated_settings.py` checks that the fields are hidden and that no code in the app (patches,
tests and translations excluded) reads them. Wiring one up later means: remove the deprecation, add the reader,
document it here and add a wiring test. No setting of the four is read today, so none is left "used".

## 5. Hardcoded values that affect behaviour

### 5.1 Stored Arabic option values

These are stored values, not labels. English and other languages show them through `card/locale/*.po` (FR-083).
They cannot be renamed without a data patch, so the target is "keep; translate", except where a value encodes a
business rule that should be a master.

| Constant / field | Values | Where | Target |
|---|---|---|---|
| `OWNED`, `THIRD_PARTY` | ملك, طرف ثالث (plus إيجار in the Select) | `constants.py:5-6`; literal "ملك" repeated in `card_monthly_card.py:366,474,547`, `equipment_transport.py:156`, `equipment_supplier_statement.py:55,57`, `equipment_suppliers_summary.py:38`, `api.py:37,142,362` | Keep values; replace the literals with `constants.OWNED` (code hygiene, no behaviour change) |
| Rental directions | مستأجَرة من مورد, مؤجَّرة لعميل, إيجار من الباطن, تشغيل داخلي | `constants.py:9-14` | Keep |
| Shifts | نهاري, ليلي | `constants.py:17-18`; literals in `settings.py:14`, `card_monthly_card.py:180`, `card_equipment.py:546` | Keep; use the constants |
| Rate bases | باليوم, بالساعة, بالشهر | `card_equipment.py:142-154`, `card_monthly_card.py:425-437` (literals) | Keep; add constants |
| Day status | عمل, إجازة, عطل, توقف من العميل (default عمل) | `card_monthly_card_day.json` `day_status`; `card_monthly_card.py:193` (any status but عمل sets 0 hours) | **Move to a master** (WP-09: Card Stop Reason with a billable flag per company, #45). Today the four statuses are fixed and never billable |
| Adjustment kinds | إضافة, خصم | `adjustments.py:13-14`; `card_adjustment_type.json` | Keep |
| Equipment status | نشطة, متوقفة, في الصيانة, منتهية | `card_equipment.json` `status`; `materials.py:28` `ENDED_STATUS`; `constants.py` `EQUIPMENT_STATUS_ENDED` (FR-122 guard) | Keep |
| Fuel / operator payer | المؤجر, الشركة | `card_equipment.json`, Card Settings | Keep |
| Diesel supplier policy | ثابت, متغير | Card Settings; `project_diesel_fill.py:20,850` | Keep |
| Asset link field name | `الأصل_في_erpnext` | `dimension.py:24`, `asset_mapping_review.py:10`, `equipment_meter_reconciliation.py:21` | Keep (field name, not a value) |

### 5.2 Numbers, tolerances and limits

| Value | Where | Meaning | Target |
|---|---|---|---|
| 12 (hours) | `card_monthly_card.py:181` `or 12` | Shift limit when the setting is 0 or empty | Card Settings already; remove the inline fallback so 0 can mean "no limit" (owner decision) |
| 260 (hours) | `card_equipment.py:152`, `card_monthly_card.py:437` `or 260` | Standard month hours | Card Settings already; should be dated (#50) |
| 0.01 | `gl/posting.py:87`, `gl/events.py:234`, `gl/journal_link.py:106`, `gl/integrity.py:572,653` | Reconciliation tolerance fallback; `integrity.py` adds 0.01 per diesel fill | Card Settings already |
| 0.01 | `card_settlement_status.py:43` `TOLERANCE` | Settlement report tolerance, independent of the setting | Read `reconciliation_tolerance` |
| 30 (days) | `materials.py:120` `or 30` | Repeat-request window | Card Settings already |
| 15 / 0 (%) | `gl/masters.py:184-185` | Rates of the item tax templates CARD creates when the company row has none ("CARD VAT 15% - <abbr>", "CARD VAT 0% - <abbr>"); an existing template is reconciled to these rates (`_reconcile_item_tax_template`) | **Card Company Settings** (VAT rate per company); a company in another tax regime must not get 15 % |
| 31 / 62 (days) | `gl/integrity.py:308-309` | Window for supplier invoices checked against a month | Card Settings (advanced) |
| 0.002 per litre | `diesel_reconciliation.py:44` `PRICE_TOLERANCE` | Diesel price match tolerance | Card Settings (diesel) |
| 1.5 | `diesel_reconciliation.py:45` `AGGREGATE_FACTOR` | An invoice above 1.5 × the largest session counts as aggregated | Card Settings (diesel) |
| 1 (litre) | `project_diesel_fill.py:146` `TOTALIZER_READ_TOLERANCE` | Totalizer reading tolerance | Keep (advisory check) |
| 0.05 / 24 | `meter_reconciliation.py:27-28` | Meter reset ratio; maximum hours per day | Keep (report heuristics) |
| 9999-12-31 | `card_equipment_assignment.py:12` `OPEN_END` | Open end of an assignment in overlap checks | Keep (technical) |
| +1 day | `transfer.py:351` `add_days(tdate, 1)` | The new assignment starts the day after the transport date | Owner decision pending (move-day rule, WP-15, #43/#121/#122) |
| 20 / 50 / 140 / 3; 25; 50 / 20 | `catalog.py:33-37`; `tool_custody.py:32`; `fitment.py:54-55` | Page sizes and text limits | Keep (UI) |

### 5.3 Names, roles and places

| Value | Where | Target |
|---|---|---|
| Role names Card Manager, Card User, Card Supervisor, Card Operator | `install.py:52-54`, `materials.py:23-26`, `fitment.py:12`, `project_diesel_fill.py:125`, `tool_custody.py:31`, `catalog.py:41` | Keep (CARD roles) |
| Accounts Manager, Accounts User, System Manager, Stock Manager | `gl/integrity.py:45-46`, `materials.py:25`, `tool_custody.py:31`, `project_diesel_fill.py:125` | Standard roles; keep. Settings already name the diesel price and supplier roles |
| "Storage" with no place | `transfer.py:279-301` `current_location` | **Card Company Settings** "initial location" (WP-06, #42) |
| Item codes CARD-RENTAL, CARD-DIESEL, CARD-TRANSPORT, CARD-RENTAL-OUT; item groups Card Services, Card Adjustments under All Item Groups; UOM Nos | `gl/masters.py:11-20,28-55`; `gl/posting.py:784` | Keep defaults; the company row can already point to other items |
| Accounting dimension Card Equipment / `card_equipment` | `dimension.py:22-23` | Keep |
| Posting source prefixes EOMC-, DSL-, TRN- | `gl/integrity.py:31-36`, DocType `autoname` | Keep (tied to naming) |
| Diesel and delivery words (Arabic and English) | `diesel_reconciliation.py:41-43` | Card Settings (diesel) if suppliers use other words |
| Legacy fuelling DocType "Fueling Log" | `meter_reconciliation.py:30-31` | Keep (read only when present) |

Currency: CARD has no hardcoded currency. Amounts follow the company currency of the ERPNext documents. There is no
currency policy for reports (#53).

## 6. Gaps against #50

| #50 criterion | State |
|---|---|
| Inventory of hardcoded constants | This file |
| Card Settings and company rows | Done (FR-013, FR-014, FR-069) |
| No hardcoded currency, accounts or hours | Accounts per company; hours are code defaults with inline fallbacks (section 5.2); VAT rates 15 / 0 hardcoded; day statuses fixed |
| Effective dates and snapshots | Missing, except card snapshots and fill prices (section 1) |
| Accounts and cost centers belong to the company | Done (FR-014 checks, FR-091) |

Follow-up work packages (each needs its own approval): WP-06 initial location, WP-08 dead settings, WP-09 stop
reasons, WP-10 dated diesel price (FR-035), plus a new item for the VAT rate per company and the site-wide warehouse
settings.
