# Source-of-truth matrix

Principle (#40): one owner per fact; a value that can be derived is derived and not typed twice. This matrix lists, for
each fact CARD handles, the record that owns it, what is derived from it, who may write the owner, and what happens to
history when it changes. Sources are the controllers and JSON named in each row.

"Derived" means a server rule overwrites the value; a client cannot set it. "Snapshot" means the value is copied at a
moment and kept even if the owner later changes.

## 1. Master and placement facts

| Fact | Owner (single source) | Derived or mirrored copies | Written by | History on change |
|---|---|---|---|---|
| Machine identity (chassis, plate) | Card Equipment | `serial_no_key`, `plate_no_key` identity keys, unique per company (`card_equipment.py` `set_identity_keys`, `validate_unique_identity`; patch `v4_1_0.backfill_equipment_identity_keys`) | Card Manager | Version log (`track_changes`) |
| Accounting asset | ERPNext Asset | Card Equipment `الأصل_في_erpnext` link; asset details copied by `sync_asset_details`; one Asset per machine (`validate_unique_asset`); the Asset carries the Card Equipment accounting dimension (`sync_asset_dimension`) | Card Manager (link) | Version log |
| Company of a machine | Card Equipment `company` | Card, fill, transport, assignment, request company are all re-read from it or from the project and must match (`validate_equipment_company`, `validate_company_change`) | Card Manager | Changing it is guarded |
| Rental direction | Card Equipment `rental_direction` (F.7: "single source of truth") | Card Monthly Card `card_direction`, mirrored read-only | Card Manager | Card keeps `direction_used` snapshot at submit |
| Supplier and customer of a machine | Card Equipment `supplier`, `default_customer` | Card `supplier`, `customer`; party registries `Card Equipment Supplier / Customer` (`party_registry`, `_sync_supplier`, `_sync_customer`) | Card Manager | Card keeps `customer_used` snapshot |
| Rates (supplier cost, customer price, internal rate) | Card Equipment (`rate`, `rate_type`, `customer_rate`, `customer_rate_night`, `internal_rate`) at permlevels 1 and 2 | Card `rate`, `customer_rate`, amounts | Card Manager with a reason (`validate_commercial_change_reason`) | Submitted card keeps `hourly_rate_used`, `customer_rate_used`, `rate_basis_used`, `daily_hours_used` (`_snapshot_settings_used`). Rates are **not dated**: a new rate applies to every later draft card. Dated agreements are **Planned** (FR-023, postponed) |
| Operator | Card Equipment `operator` (default); Card `operator` | Needs Request resolves the operator's machine (`materials.operator_equipment`) | Card Manager | Version log |
| Where the machine is now | Card Equipment Assignment in force today | Card Equipment `current_project`, `assignment_date`: derived, read only (`keep_derived_location`, `transfer.sync_equipment_location`); a conflict or gap empties them and leaves a comment | Transport on submit; Card Manager | Assignment rows are the history. A cancel undoes only what the transport wrote |
| Project of a monthly card | Card Equipment Assignment periods | Card `project`, derived from the machine's assignments for the month (`_resolve_project`); day validity from assignment periods (`transfer.validate_card_days`) | Server | Assignment history |
| Cost center of a posting line | Assignment cost center, then the source's own, then Project, then company default in Card Company Settings | Invoice line `cost_center` (`gl/posting.py` `resolve_cost_center`, `card_cost_center`, `fill_line_cost_center`, `transport_line_cost_center`). A missing or conflicting allocation refuses the build; none is assumed | Card Manager (assignment) | Version log |
| Move-day rule | Card Company Settings `move_day_rule`, per company | Copied onto the Transport when saved (`_set_move_day_rule`); empty means the day after, as before the rule existed | Card Manager | Snapshot on each transport |

## 2. Operating facts

| Fact | Owner | Derived or mirrored | Written by | History |
|---|---|---|---|---|
| Hours and days worked | Card Monthly Card Day rows | Card `working_days`, `total_working_hours`, `amount`, `customer_amount`, `net_amount`, `customer_net_amount` (recomputed in `before_validate`) | Card User | Docstatus; amend after cancel |
| Typed additions and deductions | Card Monthly Card Adjustment rows (type from Card Settings `adjustment_types`) | Totals; invoice lines and, for customers, a Net Total discount | Card User | Submitted card is final |
| Diesel litres and meter readings | Project Diesel Fill | `amount = litres x unit_price`; readings from photo extraction (`diesel_meter_extraction`) are information, not authority | Card User | Docstatus; Version |
| Diesel price | Card Settings: company schedule `Card Diesel Price` (FR-125, #46, in `[Unreleased]`), else `diesel_unit_price` of the company row | Fill `unit_price` and `price_source`; fixed on the fill (FR-002): a later price change never reprices a saved fill | Card Manager (settings); exception role (single fill) | Fill is the snapshot |
| Fill price when imported from a supplier session | The supplier's own invoice (Purchase Invoice entered separately) | `invoiced_litres`, invoice price kept for reconciliation (`diesel_invoice_reconciliation` report) | Import; accountant | Source fields guarded (`_guard_source`) |
| Transport cost bearer and amount | Equipment Transport (`cost_borne_by`, `responsibility`, `payer`, `amount`, items) | `cost_bearer`, shares per machine (`_split_amount`), `cost_basis` | Card User; Accounts Manager for the financial decision | Docstatus; decision fields locked after submit |
| Transport price per project | Card Settings `project_transport_prices` | Transport amount suggestion (`_apply_transport_price`) | Role in `transport_price_editor_role` | Version of Card Settings |

## 3. Money facts

| Fact | Owner | Derived or mirrored | Written by | History |
|---|---|---|---|---|
| Accounting entry (GL) | ERPNext, from the submitted Purchase Invoice or Sales Invoice | None in CARD. CARD never writes GL | ERPNext | Ledger reversal on cancel |
| What CARD already invoiced | GL Posting Log + GL Posting Source rows (reservation list) | Source fields `posted`, `purchase_invoice`, `sales_invoice` (set on invoice submit, cleared on cancel); `gl_posting` is display only | `card.gl.posting` and `card.gl.events` only | Log is an audit record; Cancelled rows keep their data |
| Posting amount | The invoice's `grand_total` (after submit) | Log `amount`; sources total must equal invoice `net_total` within `reconciliation_tolerance` at submit | ERPNext | Rebuild instead of editing |
| Accrual booked by hand | The Journal Entry | A Linked GL Posting Log lists the cards it recognised so they are not invoiced twice (`gl/journal_link.py`) | Accountant | Cancelling the Journal Entry frees the cards |
| Accounts, items, tax templates | Card Company Settings, per company | Invoice lines and header (`gl/posting.py`). Posting items and item tax templates are provisioned by `gl/masters.py` | Card Manager, Accounts Manager | Version of Card Settings |
| VAT | The tax template named in Card Company Settings | Invoice taxes copied from the template. CARD never infers a rate (`gl/preflight.py` refuses multi-rate templates) | Accounts Manager | Template is ERPNext's |
| Period closed | Card Settings `period_lock_date` plus ERPNext period rules | `gl/preflight.check_period_open` | Card Manager | Override logged |

## 4. Stock and parts facts

| Fact | Owner | Derived or mirrored | Written by |
|---|---|---|---|
| Stock quantities | ERPNext stock ledger (Stock Entry, Bin) | Needs review shows stock read through the caller's own rights (`materials.stock_by_item`) | ERPNext |
| What an operator asked | Equipment Needs Request | Review lines copy it and keep it as asked (`requested_qty`) | Operator |
| What management approved | Equipment Needs Review `approved_qty` | Material Request rows; draft custody handovers | Card Manager |
| Tools held by a worker | Submitted Employee Tool Custody records | Balance is computed, not stored (`materials.custody_balance`) | Store side |
| Which part fits which machine | Card Equipment Part | `fit_status` on request and review lines (`fitment.py`) | Card Manager, Card Supervisor (proposals) |

## 5. Settings precedence

Document value, then Card Company Settings row, then Card Settings, then the code default in `card/settings.py`. The
full inventory with defaults and readers is in
[SETTINGS-AND-CONSTANTS.md](../governance/SETTINGS-AND-CONSTANTS.md); it is not repeated here. Effective-dated settings
are **Planned** (#50) except the diesel price schedule.

## 6. Duplicated-truth risks found while reading

These are places where two fields can disagree. They are listed in [06-risk-register.md](06-risk-register.md).

| Pair | Why it can disagree |
|---|---|
| Card Equipment `status` and `exit_date` / `rental_end_date` | `status` is a free field; nothing derives it from the dates |
| Card Equipment `internal_rate` and the older `internal_hourly_rate` | Both exist; `card_value.internal_rate_of` prefers the first |
| Source `purchase_invoice` / `sales_invoice` and the log's membership | Kept in step by `gl/events.py` on submit, cancel and delete; a direct database edit would split them. At submit `gl/events.py` re-verifies the sources (`_verify_sources`) |
| Transport `to_location` / `from_location` (older) and `destination_*` / `source_*` | Both sets exist on the DocType; the posting query still selects the older fields |
