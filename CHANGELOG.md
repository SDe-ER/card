# Changelog

All notable changes to the Card app are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Published ≠ deployed.** A version listed here is a published GitHub release. Which version
> runs on a given site is a deployment fact, verified on that site — never inferred from this file.

Per-version documentation (complete feature inventory, comparison matrix, upgrade guidance):
[docs/releases/](docs/releases/VERSION-HISTORY.md) —
[Version History](docs/releases/VERSION-HISTORY.md) ·
[Version Comparison](docs/releases/VERSION-COMPARISON.md) ·
[Which Version Should I Use?](docs/releases/WHICH-VERSION.md)

## [Unreleased]

### Added
- **FR-145 — Draft monthly cards from approved daily logs (#44, #123, FR-022; closure plan WP-K2).** Reason: #44
  asks for automatic card generation from daily entry with no duplicate between the manual and the automatic route,
  and #123 for daily entry feeding the monthly cards; FR-142 records and approves the logs but generated nothing.
  New manual action `card.daily_log_generation.generate_monthly_cards(company, project, month, equipment=None)`
  (`methods=["POST"]`, type hints on every argument; `month` is YYYY-MM or a date of the month) and a **Generate
  monthly cards** button on an approved Card Daily Log (`card_daily_log.js`, for users who can create a Card Monthly
  Card; it shows created, updated, unchanged and submitted cards, days left out and cards not saved). It reads only
  Approved, submitted logs of the company, project and month (optionally one equipment) and creates or updates DRAFT
  Card Monthly Cards, one per equipment, project, month and shift (the card's own duplicate key): a log row's day
  shift hours and its stop data (stop reason, stopped hours, responsible party type, record and name) go to the day
  row of the day shift card, its night shift hours to the night shift card; a shift card is created only when a log
  row has hours for it; a draft card's day covered by an approved log is set from the log on every run (the day's
  notes name the log, the day name is set as the form sets it), every other day row is kept. **The approved log
  wins:** a draft day whose values differed from the log (a manual correction or an earlier log) is replaced and
  listed in `overwritten_days` (card, date, old and new hours, stopped hours and notes; also shown in the dialog). A
  day whose notes name a log that is no longer Approved (cancelled after generation) — counted only when that log is
  of the card's company and project, dated on the day and has a row for the card's equipment; any other text,
  a hand-typed log name included, is never touched or reported — is cleared on a draft card
  (hours, stop data and notes emptied; `cleared_days`) and only reported on a submitted card (`stale_days` of its
  `kept_submitted` entry). Each card is built and saved through the card's own `insert()` /
  `save()` with the user's permissions, so the card's validation runs unchanged (duplicate guard, assignment days,
  unit-component days, stop reasons and billable snapshot, rates, fiscal-year window). A submitted card is never
  changed (reported) and no card is ever submitted. Repeat-safe: a second run changes nothing (no duplicate day or
  card); a log approved later fills its day; the equipment row is locked during its cards (the card's duplicate guard
  reads without a lock), then its cards of the month are read with a locking read (`FOR UPDATE`, the latest
  committed rows) and compared with the request's snapshot: when another run changed them after this request
  started, the equipment is skipped and listed in `conflicts` ("run again"), so two concurrent runs never create a
  card twice. A missing project and another company's project get the same "not found" answer. Left out and reported, never written: a day the equipment is not on the project (yard,
  workshop, storage or another project; `card.transfer.validate_card_days`) and a day it is a component of a unit
  (`component_periods`; the day belongs on the unit's card, as `CardMonthlyCard._refuse_unit_component_days`
  requires). A machine moved during the month gets one card per project (each run names one project). A card that
  fails its own validation is rolled back alone (savepoint) and reported; a permission error stops the run.
  Authorization: the user must be allowed to create a Card Monthly Card of the company and project (probe card:
  DocPerm, Company User Permissions, `has_card_permission`) and to read Card Daily Logs (read through
  `frappe.get_list`, FR-131 company scope); project and equipment must belong to the company. Affected functions:
  new `card/daily_log_generation.py`; `card_daily_log.js` (button); `card/tests/test_bola_matrix.py` (FR-129 row for
  the new endpoint) and `docs/governance/ROLE-ACTION-MATRIX.md` (endpoint table regenerated, one row). Tests:
  `card/tests/test_daily_log_generation.py` (29) and `card/tests/test_daily_log_generation_concurrency.py` (3, two
  real connections; fails without the locking read). PR #221.
  Impact: permissions — none changed (no role, DocPerm or `ignore_permissions`); the action is limited to users who
  can already create monthly cards (Card Manager, Card User, System Manager). Accounting none (draft cards only; no
  GL, no invoice). Data: writes draft Card Monthly Cards only when a user runs the action; nothing runs by itself; no
  patch. API: one new POST endpoint. Rollback limits: code rollback removes the action and the button; the draft
  cards it created stay as ordinary draft cards (edit or delete them as usual).
- **FR-146 — Equipment Transport intake provenance (#52, #43; closure plan WP-N1).** Reason: #52 asks that a
  movement entered from paper, WhatsApp or email keeps its source, received time and original attachment, and that
  the same source never creates two records. New optional Equipment Transport fields (section "Intake source",
  collapsed, all `no_copy`, empty by default): `intake_channel` (Manual / Paper / WhatsApp / Email / Other; set to
  Manual only when another intake field is given), `intake_source_key` (external id, indexed), `intake_received_on`
  (Datetime, not in the future), `intake_evidence` (private Attach) and `intake_evidence_hash` (read only). New
  module `card/intake.py`: `apply_transport_intake` (called at the end of `EquipmentTransport.validate`),
  `check_source_key`, `warn_reused_evidence`, `claim_transport_evidence` (new `EquipmentTransport.on_update`),
  `file_sha256`. Rules: one live (draft or submitted) transport per company and source key, refused with
  `DuplicateIntakeError` after a lock on the company row and a locking read (`frappe.qb ... .for_update()`), so two
  concurrent saves cannot both pass under REPEATABLE READ; a cancelled transport frees its key (the amendment keeps
  it); two companies may share a key. The evidence must be a private JPEG/PNG/WebP/PDF of this transport (or the
  user's own upload, then claimed), checked by `card.attachment_validator`; its SHA-256 is computed on the server from
  the File bytes, and a hash sent by the client is never kept. The same evidence on another live transport of the
  company only warns (owner rule 2026-11-10: new rules warn-only or opt-in). PR #220.
  Impact: permissions none (no role, DocPerm or endpoint added; `card.intake.propose` is WP-N3); accounting none (no
  posting reads these fields); data: six new nullable columns and one index on `tabEquipment Transport`, no patch,
  existing transports keep empty values and are saved, submitted and cancelled exactly as before (no lock is taken
  without a source key); API: the new fields are readable and writable on drafts like any transport field, the hash
  is server-written. Rollback: reverting the code leaves the columns and their values in the database (unused);
  evidence files stay attached to their transports.
- **FR-142 — Card Daily Log: daily equipment hours with manager approval (#44, #123, FR-022; closure plan WP-K1).**
  Reason: #44 and #123 ask for daily entry from paper/WhatsApp and an operator/supervisor → manager approval with no
  self-approval; until now hours were entered only on the monthly card day rows. New submittable DocType **Card
  Daily Log** (header: company (required), project (required), date, site supervisor; rows **Card Daily Log Row**:
  equipment, day shift hours, night shift hours, stop reason, stopped hours, responsible party type, record and
  name (optional, the FR-118 card day-row rule through `CardMonthlyCard._normalise_responsible_party`: an empty
  type takes the stop reason's default, a Company party is the log's company and another company is refused,
  Other keeps a free-text name only), notes) and the per-company master **Card Daily Log
  Settings**: `self_approval_rule` "Warn only (daily log)" (default) / "Refuse (daily log)", and
  `require_supervisor_verification` (Check, default 0). Flow: a Card Operator (own logs only), Card Supervisor or
  Card Manager enters and submits; a Card Manager (or System Manager) then approves or returns it with a reason
  ("Returned for correction") by saving `approval_status` on the submitted log; an approved or returned log is
  final and is corrected by cancel and amend. Opt-in supervisor step: with `require_supervisor_verification` set, a
  submitted log is first "Verified by supervisor" by a Card Supervisor who is not its preparer (`verified_by/on`),
  and only then approved by a manager; the verifier counts as a preparer for the approval; a Card Supervisor may
  also return a Pending log in that mode. Every approval field (`approval_status`, `verified_by/on`,
  `approved_by/on`, `self_approved`, `return_reason`, `returned_by/on`, `submitted_by`, `edited_by`) is written by
  the server only, on every route (form save, REST insert with `docstatus` 1, `frappe.client.set_value`, bulk
  update): a draft and a submit always reset them to Pending, a change after submit is checked in
  `before_update_after_submit`, and a cancel (form, REST PUT with `docstatus` 2, savedocs, bulk) reads the stored
  approval with a row lock in `before_cancel` and keeps the stored approval fields. FR-121 style separation of
  duties: the creator, the submitter and every editor of the log and of every log of its amendment chain are its
  preparers, and so is every supervisor who verified one of them; when one of them approves, the company rule decides — "Warn only" (default, also for a company without
  a settings record) approves with a warning and marks the log `self_approved`, "Refuse" refuses (no role exempt,
  Administrator included). An approved log is cancelled only by an approver. Row rules, the same as the monthly
  card day rows and through the same functions: shift limits only warn (owner 2026-10-14; Card Settings
  `max_day_shift_hours` / `max_night_shift_hours`); a row with hours must be on an assignment of the equipment to
  the project on the log date (`card.transfer.validate_card_days`; equipment without assignment history is not
  checked, as on the card); the equipment status rule of the company (`check_equipment_status`, with the monthly
  card message); a stop reason must be an enabled reason of the log's company (`validate_downtime_fields`); day +
  night + stopped hours ≤ 24; no hours on a future date. One log per equipment, project and date (cancelled logs
  excepted): the equipment rows are locked, then the other logs are read with one locking query (`FOR UPDATE`, the
  latest committed rows), so two concurrent submits cannot both pass. Company isolation: the generic FR-131 hooks
  (already registered for Card Daily Log); every row's equipment must belong to the log's company
  (`check_child_companies`); the project's company must be the log's company; an amendment may only amend a
  cancelled log of the same company that the user can read (Frappe copies the original's attachments), and
  `card.company_scope.COMPANY_SOURCES` gains "Card Daily Log" so the `amended_from` link carries its company. Card
  Daily Log Settings is scoped by the Company User Permissions that apply to Card Daily Log (`applicable_for`
  included): `card.daily_log.settings_permission` / `settings_query_conditions`, and a DocShare of it with
  everyone or with a user outside its company is refused (`deny_cross_company_settings_share`), all registered in
  `card/hooks.py`. No
  monthly card is generated from a log yet (WP-K2). Affected functions: new `card/daily_log.py` (`prepare`,
  `validate_log`, `record_submitter`, `check_transition`, `check_cancel`, `self_approval_rule`,
  `requires_supervisor_verification`, `log_preparers`, `settings_permission`, `settings_query_conditions`), new
  controllers and `card_daily_log.js` (Verify / Approve / Return buttons); `card/company_scope.py`
  `COMPANY_SOURCES`; `card/hooks.py` (two permission entries and one DocShare validate entry for Card Daily Log Settings). Tests: `card/tests/test_daily_log.py`
  (53, including a two-connection concurrency test). `docs/governance/ROLE-ACTION-MATRIX.md` regenerated (three new
  DocType rows). PR #218.
  Impact: permissions — new DocPerms on the new DocTypes only (Card Daily Log: System Manager full; Card Manager
  full except delete; Card Supervisor read/create/write/submit/cancel/amend; Card Operator the same on own logs
  (`if_owner`); Card User read. Card Daily Log Settings: System Manager read/create/write/delete; Card Manager read);
  no existing role or DocPerm changed; no new whitelisted endpoint. Accounting none (CARD writes no GL; a log
  creates no document). Data: three new tables, nothing written to existing records, no patch. API: the new
  DocTypes' REST resources. Rollback limits: code rollback leaves the three tables and their rows (harmless,
  unused); delete the DocTypes to remove them, after K2 only if no monthly card was generated from a log.
- **FR-139 — Transport responsibility posting, per company: Hold (default) or Post (#49, #126, #43; WP-T,
  conflict C-09, owner decision O-14, PR #215).** Reason: #49 and #126 ask for customer transport charging and the
  posting of transport responsibility scenarios, while the owner decision of 2026-10-31 (FR-093, P1-2) holds every
  transport recorded with a responsibility out of the monthly build until the accountant and the tax adviser decide.
  Both now hold: new per-company setting Card Company Settings `transport_responsibility_posting` ("Hold (transport
  responsibility posting)", the default, also for an empty value and for every existing row; or "Post (transport
  responsibility posting)") and `transport_recharge_income_account` (Link Account, used by Post only). **Hold keeps
  the P1-2 filter of `card.gl.posting._supplier_sources` unchanged** (same query, same fields, same order — tested
  against a copy of the v4.7.0 query). **Post** (DRAFT standard ERPNext invoices only, through the existing monthly
  builder; no GL write, no auto-submit): on the transporter's monthly Purchase Invoice a submitted transport the
  company pays is added when the company bears it (line on its explicit cost project, place cost center or overhead
  cost center — never the origin or destination), or when its financial decision is approved: "Bill customer" (line
  on the approved billing project's cost center), "Recover from equipment supplier" by adjustment document (line
  only; the accountant issues the recovery document) or by deduction from monthly dues when the equipment supplier is
  the transporter (the line plus a negative recovery line on the same Purchase Invoice, same account and the
  company's CARD cost center; the transport reserves the net amount). On the customer's monthly Sales Invoice a
  transport whose approved decision is "Bill customer" with "Monthly invoice" adds one positive line of its
  `billing_amount` (never the transporter cost) on the billing project, with the recharge income account; a zero or
  negative amount is refused (ZATCA rule of 2026-10-15: no negative Sales Invoice line). VAT is never inferred: every
  line carries the company's CARD item tax template (FR-127 `standard_vat_rate`), as all CARD lines do. Still held in
  Post (listed as preview warnings): a pending or returned decision, "Company absorbs" (no cost project is recorded
  for the absorbed cost), a deduction from another supplier than the transporter (one transport is one supplier-side
  source), a "Separate invoice" on the customer side (the transporter line still posts), "needs review" and every
  move the company does not pay. A billing project of another company is refused. The duplicate guard is the FR-090
  one per side (GL Posting Source membership, then the invoice link on submit); the built signature and snapshot
  apply to the new lines. Transports recorded before P1-2 keep their P1-0 rule in both modes.
  Review fixes (independent accounting review of PR #215): cancelling the Purchase Invoice of a transport whose
  customer Sales Invoice is still submitted keeps it `posted` (Equipment Transport has no `sales_invoice` field, so
  `card.gl.events._other_side_still_posted` now reads the other side from its submitted GL Posting Log; other
  sources unchanged); a recovery above the transport cost is refused; the recovery deduction and the customer
  lines are split per machine in the proportions of the transport's equipment shares — only over machines with
  a positive share, the rounding remainder on the largest share, a negative part refused, so no negative Sales
  Invoice line and no part for a machine without cost; the recharge income account must be an Income account; a cancelled billing project is refused.
  Known limits (owner questions): transports held in Post ("Company absorbs", deduction from another supplier,
  "Separate invoice") have no manual-link path yet — "link supplier invoice" still refuses every P1-2 transport, so
  the accountant enters those invoices without a CARD link; the Transport Accounting Review report keeps its P1-2
  wording under Post (its status texts still say that posting waits, e.g. "Company cost recorded — Purchase
  Invoice posting waits for the accountant", "Customer billing recorded — invoicing waits for the accountant and the
  tax adviser" and "Recovery recorded — not posted until the accountant decides"); a customer-side Net Total discount (taxable card
  deductions) is apportioned by ERPNext over every line of the Sales Invoice, the transport recharge lines included
  (same VAT base; the per-line split of the discount is ERPNext's).
  Affected functions: `card.gl.posting._supplier_sources`, `_plan_monthly_posting`, `month_parties`,
  `transport_line_cost_center` (its place check moved to `_place_cost_center`, same behaviour), new
  `responsibility_line_allocation`, `_responsibility_transports`, `_customer_transports`,
  `_customer_transport_lines`, `_split_by_shares`; `card.gl.events._other_side_still_posted`; `card.gl.preflight`
  `posts_transport_responsibility`, `require_transport_recharge_account`; `card.transport_costs`
  `supplier_posting_kind`, `customer_billing_eligible`.
  Impact: permissions none (no role, DocPerm or `ignore_permissions` added; the new fields are permlevel 1 like the
  rest of the company row); accounting none under Hold; under Post more draft invoice lines, posted only after an
  accountant submits them; data: two new columns, empty on existing rows (= Hold), no patch; API: no new or changed
  endpoint (`post_month`, `rebuild_month`, `preview_month`, `posting_month_parties` keep their signatures). Not
  changed: the Transport Accounting Review report text and "link supplier invoice", which still refuses P1-2
  transports. Rollback: revert the commit; the two columns stay in the database and can be dropped only by a
  separate approved task. Drafts built under Post are ordinary CARD drafts and can be deleted (their sources are
  freed); submitted ones are reversed by cancelling the invoice (Sales Invoice: a credit note when ZATCA applies).
  After a revert, a transport already linked to a submitted Purchase Invoice stays linked.
- **FR-140 — Equipment Meter Reading: engine-hour readings per equipment (#31 D6; closure plan WP-H2).** Reason:
  #31 separates engine hours (meter) from billable hours, and O-11 D6 sets weekly meter readings by the site
  supervisor; no record of meter readings existed. New submittable DocType **Equipment Meter Reading** (naming
  `EMR-.#####`, track changes): `equipment` (Card Equipment), `company` (mandatory, read only, fetched from the
  equipment and always replaced by the equipment's company on the server), `reading_datetime`, `engine_hours`,
  `source` (Weekly reading, default / Handover reading / Service reading / Other reading), `is_meter_reset` with a
  mandatory `reset_reason`, read-only `previous_reading` / `previous_engine_hours`, a private `attachment` and
  `notes`. Rules (server, every entry point): engine hours are never negative; compared with the submitted readings
  of the same equipment just before and just after its date and time, a lower reading is refused unless it is a
  meter reset with a reason (a reset is accepted only for a lower reading), a backdated reading may not exceed the
  next one unless that one is a reset (and must stay above a later reset, so that reset stays lower), and two
  submitted readings never share a date and time; drafts and cancelled readings do not count; the check runs again
  on submit under a row lock on the Card Equipment record, so two parallel submits cannot both pass. A cancel takes
  the same lock and is refused when it would leave the next submitted reading out of sequence (lower than the new
  previous reading without a reset, or a reset without a higher previous reading). An amendment must amend a cancelled reading of the same company that the user
  may read (Frappe copies the attachments of `amended_from`). The attachment must be a private JPEG, PNG, WebP or PDF
  of this record or the user's own upload, which the reading then claims (`card.attachment_validator`). Affected
  functions: new `equipment_meter_reading.py` (`neighbour_readings`, `EquipmentMeterReading.validate`,
  `before_submit`, `before_cancel`, `on_update`). Tests: `card/tests/test_meter_reading.py`; `card/tests/test_company_scope.py`: the
  planned-DocType guard accepts Frappe's own `amended_from` self-link of a submittable DocType (any other self-link
  is still refused). `docs/governance/ROLE-ACTION-MATRIX.md`: new DocType row. PR #217.
  - Permissions: Card Manager (all), Card Supervisor (create, write, submit, cancel, amend), Card User (read, print,
    report); no DocPerm for any other role (Administrator only, as for every DocType). Company isolation through the
    generic company scope (FR-131, already registered for this DocType): a company-restricted user can neither read,
    list, create, move nor amend a reading of another company.
  - Accounting: none (no posting, no GL; CARD writes no GL). Data: one new table; nothing existing changes; the
    reading feeds nothing yet (monthly card, billable hours, diesel figures unchanged; WP-H1/H3 will read it).
  - API: the standard REST resource of the new DocType; no new whitelisted method.
  - Rollback limits: code rollback leaves the `tabEquipment Meter Reading` table and its rows (harmless); readings
    entered meanwhile stay in the database and become visible again on a later re-deploy.
  - Known limits: `previous_reading` / `previous_engine_hours` are a snapshot taken at save/submit; a reading added
    earlier or cancelled later does not update them. WP-H1/H3 must work out the sequence (and engine hours per
    period) from the submitted readings themselves, never from these fields. Engine hours only (no km meters; backlog).
    Parallel submits are proven by a lock and locking-read unit test and the reviewer's two-connection probe; a
    two-connection race test in the suite is backlog.
- **FR-141 — Dated rate agreements, built opt-in and not wired (#41; closure plan WP-M1, conflict C-16, owner
  decision O-08 default).** Reason: #41 needs effective agreements per equipment, party and project, and "no automatic
  billing when several agreements match"; FR-023 (dated agreements) was postponed by the owner on 2026-10-19, so the
  model is added unused and changes nothing until the opt-in wiring (WP-M2..M4) is merged and enabled per company.
  New submittable DocType Card Rate Agreement (company; an equipment or an equipment type; supplier and/or customer;
  optional project and work zone; valid from / valid to, empty end = open-ended; rates per hour, day, month and
  quantity unit in the company currency) and child table Card Agreement Responsibility (cost category Rental /
  Diesel / Transport / Maintenance, paid by Company / Customer / Supplier / Other party, share %, optional single
  equipment; shares total 100% per category). New `card/agreements.py`: `resolve(company, equipment, party, date,
  project=None, zone=None)` returns None when nothing matches, the agreement when one does, and raises
  `AmbiguousAgreementError` when several do (CARD never chooses); every filter runs in SQL (`valid_from` and
  `valid_to` indexed); the party is required; `project=None` / `zone=None` match only agreements without a project /
  zone; the zone is compared stripped and case-folded (`normalise_zone`); a zero rate means no rate for that basis.
  `validate_agreement`, `check_overlap` (same key and overlapping dates refused; at submit the company row is locked
  and the clashing agreements are read with a locking read, so the second of two concurrent submits sees the
  first); an agreement for one equipment takes that equipment's type; company checks on equipment, project,
  amendment and child rows (`card.company_scope.check_child_companies`); a responsibility row may name an equipment
  only on a type-level agreement. A changed rate is a new agreement (no field is allow-on-submit). Nothing calls
  `resolve()` yet. `test_company_scope` guard skips Frappe's own `amended_from` self-link; ROLE-ACTION-MATRIX DocType
  table regenerated. Tests: `card/tests/test_agreements_resolve.py`, `card/tests/test_agreements_concurrency.py`
  (two committed concurrent submits). PR #216.
  Impact: permissions: new DocType only (System Manager full; Card Manager create, write, submit, cancel, amend;
  Accounts Manager and Card User read; no existing role or DocPerm changed), records isolated by company through the
  FR-131 hooks; accounting none (CARD writes no GL; posting does not read agreements); data: two new tables (indexes
  on `valid_from`, `valid_to`), no patch,
  existing records untouched; API: standard REST of the new DocType, no whitelisted method. Rollback limits: code
  rollback leaves the two tables and any agreements entered (unused by older code, harmless).
- **FR-138 — Day billing basis per equipment: "Prorated by hours" (default) or "Full day" (#123, #44; WP-AB,
  conflict C-05, owner decision O-06 default).** Reason: FR-024 left the per-day ("باليوم") method open between the
  current hours-prorated amount and full-day billing (see "Planned" below); O-06 keeps prorated as the default and
  allows full-day billing per equipment where the contract says so. Card Equipment gets `day_billing_basis` (Select,
  "Prorated by hours" / "Full day", default "Prorated by hours", permlevel 1, a commercial field: a change needs a
  commercial change reason). Card Monthly Card gets `day_billing_basis` (read-only Select, same options, mirrored live
  from the equipment like the rates) and `day_billing_basis_used` (read-only Select, same options, no copy,
  snapshotted on submit); both are Selects so their values are translated. Rule: a side whose rate
  basis is "باليوم" under "Full day" is billed `billed days x rate`, where billed days = operating days + days billed
  only by billable stopped hours of that side (FR-134); the hours of a day no longer change its amount. Every other
  case (default basis, an empty value on equipment saved before FR-138, hourly or monthly rates) keeps
  `billed hours x hourly rate` exactly as before. On a sub-rental card each side applies the basis to its own rate
  basis and billed days. Submitted cards are never repriced (no recompute after submit; the snapshot records the
  basis used); a draft follows the equipment on its next save; an amended card is priced and snapshotted with the
  equipment's basis at its own submit. The Equipment Supplier Statement and the Equipment Customer Statement show a "Day
  billing basis" column (per-day cards only: the snapshot of a submitted card, the current basis of a draft).
  On the customer statement a "Full day" card's hourly rate is its customer amount over its billed hours
  (operating + customer-side billable stopped hours), as the supplier statement already shows it, instead of the
  nominal `customer_rate_used`; prorated cards keep the snapshot rate. The draft form preview
  (`card_monthly_card.js`) mirrors `bills_full_days` for the supplier amount. Affected functions:
  `card/card_value.py` (new `DAY_BASIS_PRORATED`, `DAY_BASIS_FULL_DAY`, `day_billing_basis`, `bills_full_days`);
  `CardMonthlyCard.before_validate` (amount and customer amount), `_snapshot_settings_used`;
  `card_equipment.py` `COMMERCIAL_FIELDS`; `equipment_supplier_statement.execute`;
  `equipment_customer_statement.execute`; `card_monthly_card.js` `card_load_hourly`, `card_calc`; patch
  `card.patches.v4_8_0.default_day_billing_basis` (fills the default on equipment with an empty value, idempotent,
  no modified change). Tests: `card/tests/test_day_billing_basis.py`. PR #214.
  Impact: permissions none (the equipment field is permlevel 1 like the rates; the card fields are level 0 and
  carry no amount; no role or DocPerm change); accounting none by default (amounts unchanged unless an equipment is
  set to "Full day"; postings take the card amounts as before; CARD writes no GL); data: one new column on
  `tabCard Equipment` (filled with the default by the patch), two new nullable columns on `tabCard Monthly Card`;
  cards submitted before FR-138 keep an empty `day_billing_basis_used`, read as "Prorated by hours" (they were
  priced so); API: the new fields appear in the REST documents. Known limits (O-06 decision text): one basis
  per equipment applies to both sides of a sub-rental card (a contract with a full-day supplier and a prorated
  customer, or the reverse, needs a later per-side option); a day-shift and a night-shift card of the same
  machine and day are each billed a full day under "Full day" (each shift card stands alone, as before); hours
  over `daily_hours` earn nothing extra under "Full day" and there is no overtime (FR-008 / WP-L1, O-13);
  `hourly_rate_used` / `customer_rate_used` keep the nominal rate / daily hours on a "Full day" card (the
  statements show the effective rate); the form preview treats every billable stop reason as Both until saved
  (FR-134 limit). Rollback limits: code rollback
  leaves the columns and their values (harmless); a card priced "Full day" keeps its stored amounts and would be
  repriced prorated on its next draft save only.
- **FR-132 — Fill price snapshot: currency, unit and valid-from on each diesel fill (#46, supports #124; WP-X,
  conflict C-18).** Reason: #46 asks for the applied price *and* its currency/unit snapshot on each fill; until now a
  fill stored only `unit_price`, `price_source` and `company_price`. New read-only, no-copy fields on Project Diesel
  Fill: `price_currency` (Link Currency), `price_uom` (Link UOM) and `price_valid_from` (Date). They describe
  `company_price` and are set where `diesel_price()` resolves it: from the Diesel price schedule row (its currency,
  else the company currency; its unit; its valid from), or for the company's `diesel_unit_price` (no dated row) the
  company currency with no unit and no date. An empty unit means per litre (the price label); no unit conversion and
  no currency conversion. Wherever the fill keeps its earlier company price (an unchanged price exception, a saved
  Company Price draft) it keeps the earlier snapshot too; submitted and cancelled fills never change; an amendment
  resolves its own. Card Diesel Price gets `fuel_type` (Select, one option "Diesel", default "Diesel"); it is
  informative only: the price lookup and the one-price-per-company-and-date rule are unchanged. Affected functions:
  `project_diesel_fill.py` new `diesel_price_details`, `_scheduled_price_row`, `ProjectDieselFill._set_price_snapshot`;
  `diesel_price` and `scheduled_diesel_price` now read through them (same values); `_apply_price`. Tests:
  `card/tests/test_fill_price_snapshot.py`. PR #209.
  Impact: permissions none (fields follow the fill's DocPerms, permlevel 0, as `unit_price`); accounting none (the
  price, the amount and the posting are unchanged; CARD writes no GL); data: three new nullable columns on
  `tabProject Diesel Fill`, fills saved before this change keep an empty snapshot (no backfill); one new column on
  `tabCard Diesel Price` whose database default fills "Diesel" into existing rows on migrate (no patch); API: the
  new fields appear in the fill's REST document; `get_diesel_price_context` unchanged. Rollback limits: code rollback
  leaves the extra columns and their values in the database (harmless; Frappe ignores columns not in the DocType);
  nothing else to undo.
- **FR-131: generic company scope for the planned CARD DocTypes** (closure plan WP-HK; enabler for #31, #35, #41,
  #44, #49, #52). Reason: the close-all packages add nine DocTypes, and each needs the company isolation of the
  existing CARD hooks; registering it once keeps later packages out of `card/hooks.py`. New `card/company_scope.py`:
  `has_company_permission` (record check: the company sent and stored, plus the company of each new or changed
  top-level Link to Card Equipment, Project, Card Monthly Card or Warehouse; for a DocType without a `company` field
  also the stored link; a new record of a restricted user that has no company yet is refused; CARD-module DocTypes
  only), `company_query_conditions` (list twin), `deny_cross_company_share` (DocShare validate) and the package
  helper `check_child_companies` (companies on child-table rows are each package's own responsibility).
  `card/hooks.py` registers them for Equipment Meter Reading, Card Daily Log, Card Rate Agreement, Card Period Run,
  Card Approval Delegation, Diesel Dispense, Tank Dip Reading, Equipment Operating Group and Card Intake Record; the
  DocShare validate hook becomes a list (the diesel fill check is kept first). PR #208 (branch `feat/company-scope-hooks`).
  - Permissions: deny-only; no role, DocPerm or User Permission change. Users without a company restriction and
    every existing DocType are not affected (their own hooks are unchanged). Hooks of DocTypes that do not exist yet
    are inert.
  - Accounting, data, API: none (no field, patch, endpoint or GL change).
  - Rollback limits: none; reverting the commit removes the hooks. A planned DocType merged after this change loses
    its company isolation if this change is reverted.
- **Card Reviewer role** (FR-137, #35 Q2, PR #207). Reason: the governance workflow (#35 G1) needs a reviewer
  role separate from the approver. `card/install.py`: `CARD_REVIEWER_ROLE` added to `CARD_ROLES`, so
  `ensure_card_roles()` (before_install and every roles patch) creates it with Desk access; new idempotent patch
  `card.patches.v4_8_0.ensure_card_reviewer_role` (new package `card/patches/v4_8_0`) creates it on existing sites.
  Impact: permissions none (no DocPerm names the role and no user is given it; later governance packages wire it and
  the owner assigns it); accounting none; data one Role record; API none. Default behaviour unchanged.
  Tests: `card/tests/test_card_reviewer_role.py`. Rollback: reverting the code leaves the unused Role record; it can
  be disabled or deleted by hand while no user holds it.
- **Main store, tool custody store and repeated-request window per company (FR-135, #50, #126, PR #211).** Reason:
  the materials warehouses and the repeat window were site-wide only (#50 "no hardcoded … per company"). Card
  Company Settings gets a Materials section with `store_warehouse`, `custody_warehouse` and `repeat_request_days`
  (all optional, empty by default). Readers (`card.settings.store_warehouse`, `custody_warehouse`,
  `repeat_request_days`) use the company value and fall back to the Card Settings value when it is empty (no row,
  no warehouse, 0 days), so the default is unchanged. Affected functions: `card.materials.repeat_days`,
  `last_asked_on` (company of the machine), `pull_requests`, `approve_review` (company of the review);
  `EmployeeToolCustody.validate`, `_check_company`, `_make_stock_entry` (company of the employee);
  `card.tool_custody.context` (new `default_stores` per permitted company; `default_store` unchanged), `move`
  (the store of the worker's company, set after the create check) and the new read-only
  `card.tool_custody.employee_company` (GET, screen role, employee in the `employee_query` scope): when the
  Employee changes, the Tool Custody dialog sets that company's store and searches only its stores.
  On Card Settings save (`validate_company_warehouses`, one call added in `CardSettings.validate`) a company
  warehouse must be an enabled, non-group warehouse of its row's company, and a company's custody store in force
  cannot change while any of its tools is held in custody. At read time a foreign-company warehouse is refused
  with a message that names neither the other company nor its warehouse (the screen does not offer it). Labels:
  "VAT 15% item tax template" → "VAT item tax template (company rate)"; its description, the Addition/Deduction
  Types description and the Card Adjustment Type `taxable` description no longer name 15% (FR-127 backlog LOW-3;
  the rate comes from the company's tax templates). Impact: permissions none (new child fields at permlevel 1 like the
  rest of the row, no role or DocPerm change); accounting none (CARD writes no GL; Stock Entries use the chosen
  warehouses); data: three new nullable columns, no patch, no existing value changed; API: `context` returns one
  more key, one new GET endpoint (in the role and action matrix). Rollback limits: reverting the code ignores the columns (the site values apply again); change a
  company's custody store only when no tool of that company is held in custody, or a Return/Loss reads stock from
  the new store.
- **Downtime governance** (FR-134, #45, PR #212, conflict C-07, owner decision O-03 default). Reason: #45 allows a downtime
  charge only as an explicit, approved manual addition with reason, party, agreement reference and audit trail, but a
  billable stop reason (FR-118) billed every stopped hour on both sides with no recorded approval.
  - Card Stop Reason: `billable_side` (Both / Supplier / Customer, default Both) and `billable_approval_reason`
    (required when billing is switched on or its side changes; switching an older billable reason off or editing it
    needs none; `track_changes` stays on). `billable` stays off by default.
  - Card Monthly Card (`before_validate`, `_resolve_stop_reasons`): a billable reason bills its stopped hours on its
    side only; on a card that does not bill that side the day row's `reason_billable` is 0. New read-only
    `supplier_billable_stopped_hours` and `customer_billable_stopped_hours` store the hours per side;
    `billable_stopped_hours` is kept unchanged for compatibility. A sub-rental card with a one-sided reason gets a
    review warning.
  - Equipment Supplier Statement, Equipment Customer Statement, Equipment Suppliers Summary and Equipment Customers
    Summary read the stopped hours of their own side (`card_stop_reason.side_stopped_hours`), also in the hourly
    rate (amount over operating + stopped hours); a card saved before FR-134 falls back to `billable_stopped_hours`.
  - Card Adjustment Type: flag `is_downtime_charge` (default off). Card Monthly Card Adjustment: `stop_reason`,
    `responsible_party_type`, `responsible_party`, `responsible_party_name`, `agreement_reference`; a row of a
    downtime-charge type must name an enabled stop reason of the card's company, the responsible party and the
    agreement reference (`card.adjustments.validate_downtime_fields`). A stop reason of another company is refused on
    any row. A downtime charge whose reason is also billed on the same side through the card's days is flagged for
    review (not blocked).
  - Card Monthly Card Adjustment (`validate`): a row saved or inserted on its own (REST PUT/POST on the row) may not
    change the amount, type, side or a downtime field; the change must go through the card's save, so the card's
    rules run and its Version history shows it (as #59 for unit components). A description-only edit still works.
  - Patch `v4_8_0.stop_reason_billable_side`: sets Both on existing reasons without a side (idempotent).
  - Patch `v4_8_0.backfill_side_stopped_hours`: on cards with billable stopped hours and no per-side figure, sets both
    sides to `billable_stopped_hours` (every reason billed both sides before FR-134); amounts, day rows and the
    modified time are unchanged, so no card is repriced (idempotent).
  - `docs/governance/DOWNTIME-MINIMUM-GUARANTEE.md`: the minimum-guarantee assessment #45 asks for.
  - PR #212.
  - Impact: permissions none (no role or DocPerm changed); accounting none by default (no reason is billable, no type
    is flagged; a downtime charge is an ordinary typed addition with the type's account and tax); data: new columns,
    existing reasons get side Both, the per-side stopped hours of existing cards are filled from the total, no amount or
    day row is written; API: new optional fields on the adjustment rows and two read-only card fields; a reason
    switched to billable through the API without an approval reason is refused; a direct REST write of a guarded
    adjustment-row field is refused.
  - Rollback limits: the new columns stay after a code rollback; a one-sided reason bills both sides again after a
    rollback; the statements then read `billable_stopped_hours` again.
- **FR-020 `min_hours` retired** (FR-134, #45, PR #212). Reason: no code reads it and CARD implements no minimum guarantee
  (O-03; see `DOWNTIME-MINIMUM-GUARANTEE.md`). Card Equipment `min_hours` is hidden, read only and labelled
  "Deprecated – not used" (Arabic «مُهمَل – غير مستخدم» in `ar.po`; the same msgid of the FR-124 settings now reads
  «مُهمَل» instead of «متوقف», which also means "stopped"); the column and stored values are kept. Impact: none on permissions,
  accounting, data or the API. Rollback: restore the label.
- **#54 acceptance suite: GL neutrality, two companies with two currencies, month end under a site time zone,
  POST-only writers** (FR-136, #54, #53, #40; branch `feat/acceptance-suite`, PR #210).
  Reason: the #54 acceptance tests and the test-matrix rows 1, 2, 4, 14 and 15 of
  `docs/architecture/07-international-test-matrix.md` were missing (risks R-16, R-26). New tests only:
  `card/tests/test_gl_neutrality.py` (static scan: no production module writes GL Entry, Payment Ledger Entry, Stock
  Ledger Entry or Account Closing Balance rows by document, `frappe.db`, raw SQL or query builder, or calls an ERPNext
  ledger writer; submit and cancel of monthly card, diesel fill and transport, and the draft monthly posting, add no
  ledger row; the Purchase Invoice submit adds only its own balanced rows; a second active posting log of the same
  party-month is refused by the unique `posting_key` in the database), `test_two_currency_posting.py` (a real second
  company in another currency, one supplier for both: each posting takes only its company's sources, is in its
  company currency at rate 1 against its own payable, expense accounts, cost centers and project, and posts ledger rows
  of its company and currency only), `test_month_end_timezone.py` (one UTC instant that is already 1 October in UTC+3 and
  UTC+14 and still 30 September in UTC-7 and UTC-10: site-local today, the future-day check of a card, the number cards'
  "last month", month ends 28/29/30/31, posting dated the month end after local midnight, period lock by date),
  `test_writer_methods_post.py` (every `@frappe.whitelist` names `methods=`; every writer of the FR-129 matrix allows
  POST only and Frappe refuses its GET; every GET endpoint is read-only in the matrix and has no direct write call).
  Known limit: the writer test sees only write calls made directly in an endpoint's body; a write reached through a
  helper is caught only by the FR-129 run-time no-write test. Impact: tests only; no change to permissions,
  accounting, data or the API. Rollback: revert the commit.
- **Posting Source Integrity report** (FR-136, PR #210, risk R-25, #54). Reason: a source's invoice link and `posted` flag are
  written with `db.set_value` on invoice submit, so a direct database edit, an import or an older version can split a
  source from its GL Posting Log without a trace. New read-only Script Report (System Manager, Accounts Manager; on the
  CARD Reports sidebar): for one company the user may see and a period, every monthly card, diesel fill and transport
  that a posting touched, with the check result: invoice link without a submitted log, link to another invoice than the
  log's, submitted log without the link, more than one submitted posting of a side, linked invoice missing or not
  submitted, `posted` flag out of step, cancelled source still posted; and log rows whose source no longer exists. It
  changes, links, posts and repairs nothing. Affected: new `card/card/report/posting_source_integrity/*`,
  `card/card/sidebar/card_reports/card_reports.json`. Impact: a new report for two existing roles; no DocPerm or role
  change; no accounting, data or API change. Rollback: revert the commit; the Report record stays on a migrated site until it is
  deleted by hand (it only reads).

### Changed
- **Reports label money with the company currency** (FR-136, PR #210, #53, owner default O-17: company currency only,
  labelled, no conversion). Reason: a Currency column without a currency shows the site's default symbol
  (`frappe.meta.get_field_currency`), so a second company in another currency saw its amounts with the wrong symbol. New
  `card/report_currency.py`: the decorator `company_currency_report` on the `execute` of the 15 single-company CARD
  reports with money (Card Settlement Status, Diesel Invoice Reconciliation, Equipment Customer Statement, Equipment
  Customers Summary, Equipment Diesel Consumption, Equipment Expenses Without Equipment, Equipment Maintenance Cost,
  Equipment Partial Margin, Equipment Supplier Statement, Equipment Suppliers Summary, Operating Cost by Project,
  Transport Accounting Review, Transport Cost by Project, Unbilled Card Work, Posting Source Integrity) resolves the
  company the report ran for with the report's own doctypes and sets each Currency column without `options` to the row
  field `currency`, each dict row's `currency` and each Currency summary tile's `currency` to that company's default
  currency; Equipment Consumption, which spans the permitted companies, adds each row's company and its currency.
  Values, column order and labels are unchanged; nothing is converted. Impact: display only for a one-currency site
  (the symbol is the same); no permission, accounting, data or API change; report rows carry one more key
  (`currency`; Equipment Consumption also `company`). Known limits: a report total row keeps the site default
  symbol; server-side formatting (export, print) of Equipment Consumption formats every row with one currency; card
  and fill form fields are unchanged. Rollback: revert the commit.

### Security
- **FR-142 / FR-140 — a cancel can no longer rewrite a Card Daily Log or an Equipment Meter Reading.** Reason: Frappe
  skips `validate` and `validate_update_after_submit` on a cancel and stores the fields and child rows the request
  sends (`frappe/model/document.py`); reproduced on a sandbox site: a REST PUT `{"docstatus": 2, ...}`, a savedocs
  Cancel with a modified document and a bulk update with `docstatus` 2 and data each stored changed hours rows, log
  date and notes on a cancelled daily log, and a REST PUT changed the engine hours, the reading time and the notes
  of a cancelled meter reading. Fix: both cancels now run the generic FR-123 guard of `card/cancel_reason.py`
  (`_refuse_changes`, `CancelChangesDocumentError`, already used by the monthly card): a cancel that changes any
  stored field or row is refused and the document stays submitted. The daily log first restores its server-written
  approval fields, preparers and editors from the database (FR-142 behaviour, unchanged) and then refuses any other
  change. No cancel reason is required on these DocTypes (unchanged). Affected functions: `card.daily_log.check_cancel`,
  `EquipmentMeterReading.before_cancel`. Tests: `test_daily_log.py` (REST PUT with rows, date, notes; savedocs with a
  row and the notes; bulk update with data; plain cancels still work), `test_meter_reading.py` (REST PUT, savedocs,
  bulk; plain cancel). PR #226.
  Also: Frappe checks `amended_from` on insert only, so a save (`frappe.client.save`, `frappe.client.set_value`)
  could clear or change it on a draft; reproduced on a Card Daily Log, where a cleared link dropped the earlier
  versions' preparers and let a manager who edited an earlier version approve the amendment under Refuse. A save of
  an existing Card Daily Log or Equipment Meter Reading now keeps the stored `amended_from`
  (`card.daily_log.prepare`, `EquipmentMeterReading._validate_amended_from`); tests clear it by `client.save` and by
  `set_value` and the approval stays refused, and set it on an existing record and it stays empty.
  Review hardening of the shared guard (`card/cancel_reason.py` `_changed_field`, `_rows_changed`, `_norm`,
  `_refuse_changes`): Frappe also skips `validate_constants` on a cancel and `db_update` writes every column, so a
  cancel could still rewrite the document's `owner` / `creation` and each row's `idx` (row order), `owner` and
  `creation`; reproduced on Equipment Meter Reading and Card Daily Log. These standard columns are now compared
  too; float fields are compared at 9 decimals, the stored precision (a change of 0.0000001 was accepted). The
  hardening also applies to the FR-123 doctypes (Card Monthly Card, Equipment Transport, Project Diesel Fill),
  whose message is unchanged; Card Daily Log and Equipment Meter Reading use a new neutral message ("... cannot
  be cancelled with changes: ... differs from the stored record.", Arabic added). Tests: owner and creation on the
  log, the reading and the three FR-123 doctypes; added, removed, reordered, emptied rows, swapped `idx` and a forged
  row owner or creation on the log; 100.0000001 engine hours on the reading.
  Impact: permissions none; accounting none; data: a cancel request that also changes the document is refused
  (a plain cancel is unchanged), and a save no longer changes `amended_from`; API: such a cancel request now fails
  with `CancelChangesDocumentError`, and a sent `amended_from` on an update is ignored. Rollback limits:
  code only; nothing stored to undo.
- **Card Settings company scope (FR-133, #50, closure plan R-14 / C-19, owner O-19 default-on). PR #213.** Reason:
  the per-company rows of the Card Settings Single were all-or-nothing for a company-restricted user: with a Company
  User Permission for every doctype Frappe 16 refused him the whole form as soon as another company had a row; with
  one limited to CARD documents he read every company's rows (accounts, items, adjustment types, diesel prices) and
  their change history. Now, for a user with a Company User Permission that applies to CARD (not Administrator, not
  System Manager):
  - reads of the Single (Desk form, REST v1/v2, `frappe.client.get`, save replies of `savedocs`,
    `frappe.client.save` / `set_value` / `insert` and REST v1 PUT) carry only his companies' `company_settings`,
    `adjustment_types` and `diesel_price_schedule` rows; the form shows a note;
  - the form timeline (Version rows, via overrides of `frappe.desk.form.load.getdoc` and `get_docinfo` that wrap
    the Frappe methods, and the `savedocs` reply) carries no added, removed, changed or moved row of another company;
  - a save by him puts the stored rows of the other companies back unchanged at their stored position (never
    deleted); a changed copy, a new row or a row moved to another company is refused; he cannot change any
    site-wide (non-table) field; unchanged hidden rows are not re-validated or named in a message (every rule is
    per company, so his own rows, including the FR-125 one-price-per-date rule, are checked in full);
  - a child row read on its own, and the child-table list, value and report-view reads (`frappe.client.get_list`,
    `get_value`, `frappe.desk.reportview.get` with `parent="Card Settings"`), are refused while another company has a
    row (`has_permission` hook on Card Settings; Frappe 16 applies no list condition to a child table of a Single,
    so the `permission_query_conditions` added for the three child DocTypes are a second layer only).
  System Manager, Administrator, users without a Company User Permission and server code (`frappe.get_doc`,
  `frappe.get_all`, postings) read every row as before. Affected functions: `CardSettings.has_permission`,
  `apply_fieldlevel_read_permissions`, `before_validate` (`_reattach_hidden_company_rows`), `on_change`,
  `validate` (`_rows`), `_validate_company_scope`; new `settings_company_scope`, `settings_row_readable`,
  `has_settings_permission`, `settings_row_query_conditions`, `getdoc`, `get_docinfo` (via `_previous_override`),
  `scope_docinfo_versions`, `_ScopedRows` (FR-135 warehouse check on visible rows);
  `has_permission` of Card Company Settings, Card Adjustment Type and Card Diesel Price; `card/hooks.py`
  (`has_permission`, `permission_query_conditions`, `override_whitelisted_methods`); `card_settings.js` (note).
  Impact: permissions — Frappe's User Permission check on the Single runs on the user's companies' rows only, so a
  company-restricted Accounts Manager can open Card Settings and save his companies' rows (before: refused while
  another company had a row); he can no longer change site-wide fields nor read child rows on their own; no role,
  DocPerm or permlevel changed. Accounting: none (no GL write; posting reads unchanged). Data: none (no patch, no
  schema change; rows only re-attached, never rewritten). API: readers with a Company restriction get fewer rows and
  a filtered timeline; the two Desk load methods are overridden for every doctype but change only the Card Settings
  response. Known limits: (1) the two overrides wrap the override registered before CARD's
  (`override_whitelisted_methods` chain; Frappe calls only the last one), so DAWM's own `getdoc` /
  `get_docinfo` filter (installed before CARD) keeps running; with no earlier override they call Frappe's
  method; a re-entry calls Frappe's method (no loop). An app installed after CARD that overrides the same methods
  without calling the previous one would disable both filters. (2) The reply object of a save is filtered in
  `on_change` (the document cache is already cleared then; nothing is written): Webhooks, Notifications and Server
  Scripts that run after `on_change` on Card Settings during a restricted user's save see only his rows.
  Deploy preconditions: on Production `frappe.get_hooks("override_whitelisted_methods")` for both keys lists the
  DAWM entry, then the CARD entry; no Webhook, Notification or Server Script exists on Card Settings.
  Rollback: revert the commits; no data to restore.
- **Child-table rows follow the level of their table; the Card Settings timeline follows the reader's level
  (FR-148, SEC-1). PR #227.** Reason: Frappe 16 checks the fields of a child row against the child DocType's own
  `permlevel` on the child list routes (`frappe.client.get_list` / `get_value` with `parent=`,
  `frappe.desk.reportview` with a `` `tab<Child>`.`field` `` column or a child-field filter). It does not apply the
  level of the parent's Table field there; the form and `frappe.client.get` do. Four CARD tables above level 0 had
  child DocTypes whose fields were all at level 0. What leaked, with the DocPerms of the code:
  **Card Equipment `components`** (level 1; Card Equipment Component: component, role, from/to date, change reason)
  to **Card Supervisor** (level 0 only), through all three routes, the report-view filter and the form's change
  history; **Card Settings `diesel_price_schedule`** (level 1; Card Diesel Price: company, fuel type, valid from,
  unit price, currency, unit) to **Card Manager** (levels 0 and 2), through `get_list` / `get_value` and the Card
  Settings change history (`getdoc` / `get_docinfo` returned the Version rows with the full diesel rows).
  **Card Settings `project_transport_prices`** and **`location_cost_centers`** (level 2) had the same gap, but no
  role of the code reads Card Settings at level 0 without level 2. Card Operator, Card User (Card Settings),
  Card Reviewer and Accounts User have no read on these parents.
  Fix 1 (schema): every field of Card Equipment Component and Card Diesel Price is at level 1, every field of Card
  Project Transport Price and Card Location Cost Center at level 2, the level of their only table (no child DocType
  is shared by tables at different levels); no role, DocPerm, hook or data change.
  Fix 2 (Card Settings timeline): new `mask_docinfo_versions_by_level()` in
  `card/card/doctype/card_settings/card_settings.py`, run by the existing FR-133 overrides `getdoc` /
  `get_docinfo` and by the form save (`apply_fieldlevel_read_permissions`), after the FR-133 company filter: per
  reader, the values of every Card Settings field and child row at a level he cannot read are replaced by the
  `card/field_privacy.py` mask in `changed`, `added`, `removed` and `row_changed`; who changed what and when stays.
  The Versions are stored unmasked, so a reader of the level (Accounts Manager) sees the real values; Card Settings
  is not added to the write-time `PRIVATE_DOCTYPES` (the owner's 2026-10-31 rule is unchanged).
  Affected: the four child DocType JSONs; `card_settings.py` (`getdoc`, `get_docinfo`,
  `apply_fieldlevel_read_permissions`, new `_hidden_settings_fields`, `mask_docinfo_versions_by_level`,
  `_masked_version_data`); new `card/tests/test_child_permlevel_leak.py` (guard driven by an enumeration of every
  CARD DocType and by the installed meta; shared-child check; role probes for every CARD role, Accounts Manager,
  Accounts User and a test-only level-0 role on the three routes, the report-view filter and the form; report view
  for permitted readers; server reads; component history; Card Settings timeline masked for Card Manager and for a
  level-0 reader, real values for Accounts Manager, stored Version unmasked; prints; a writer without the level
  cannot overwrite or empty the rows through `savedocs` or `frappe.client.save`); `card/tests/test_equipment_g2.py`
  (the #59 Version check now expects the masked component row).
  Impact on permissions: level-0-only readers lose the plain field values on the routes listed under "Closed";
  readers of the table's level keep the form, the print, report view (child columns and filters) and every server
  path (`frappe.get_all` / `frappe.db`, used by the posting, transport price, diesel price, component and location
  history code). Two Frappe 16 behaviours to know: (1) `frappe.client.get_list` / `get_value` on a child DocType
  return no field above level 0 to anyone, readers of the level included (`frappe/desk/reportview.py`
  `validate_fields`); no CARD Desk script, report, print or CARD Mobile screen reads these rows that way (Card
  Company Settings has behaved so since v1.2.2). (2) The change history of Card Equipment masks every field above
  level 0 for every reader (`card/field_privacy.py`, owner decision 2026-10-31): component row changes in new
  Versions keep who and when, not the values.
  **Closed** for a level-0-only reader of the parent (tests and sandbox probes, every fixed table): plain child
  fields selected through `frappe.client.get_list` / `get_value` with `parent=`; report-view child columns of a
  non-Single parent; report-view filters on child fields of the parent query (PermissionError); the form,
  `frappe.client.get` and prints; the Card Equipment change history from now on; the Card Settings change history
  (masked per reader on `getdoc`, `get_docinfo` and the form save, old Versions included).
  **Still open (Frappe 16 core).** Queries on the child DocType itself with `parent=<Parent>`, through
  `frappe.client.get_list` / `get_value`, `frappe.desk.reportview.get` / `get_list` / `get_count` (doctype = the
  child) and REST v1 `/api/resource/<Child>?parent=<Parent>`, still accept filters, `order_by` and `group_by` on
  child fields and aggregate fields (`{"MIN"|"MAX": "<field>"}`). Until Frappe core is fixed, a determined level-0
  reader can still read every hidden field of every child row, one call at a time: with a `name=<row>` filter and a
  `{"MIN"|"MAX": field}` aggregate, or prefix by prefix with a LIKE filter on `frappe.desk.reportview.get`. REST v2
  (`/api/v2/document/<Child>`) refuses both. Cause: `frappe/database/query.py` skips the field-level check when the
  queried DocType has no permissions of its own, as every child DocType (`query.py:1031`; the filter and order-by
  checks of `:1374` pass no parent; the permission query conditions of `:1706-1709` are those of the parent, so a
  `permission_query_conditions` hook on the child is not applied), and `frappe/desk/reportview.py`
  `validate_fields` skips aggregate (dict) fields (`reportview.py:153`) and checks the child's levels against the
  child DocType itself (`:177`). Owner options: **Card Equipment** (not a Single): no clean CARD-only mitigation exists; an
  `override_whitelisted_methods` entry would cover the `/api/method/...` routes only, because REST v1
  `/api/resource` calls `frappe.client.get_list` directly, and `before_request` hooks run before token
  authentication; an upstream Frappe fix is needed. **Card Settings** (a Single): every child-query route reaches
  the CARD `has_permission` hook with a lazy Card Settings document for ptype select or read
  (`frappe/permissions.py:120-129` → `:903-910` → `:135-136` → `:239`); refusing that lazy-document check to a
  reader without a table's level would close the aggregate read and the filter oracle on Card Diesel Price (and on
  the level-2 tables), at a cost: for Card Manager, `frappe.get_print("Card Settings")`,
  `frappe.client.get_single_value` and a document-less `frappe.has_permission("Card Settings")` would be refused.
  Not implemented: it needs the owner's decision. Production context (from the code at `e566174` and a read-only
  check on 2026-11-10: no Custom DocPerm exists on Card Settings or Card Equipment): the level-2 tables are not
  reachable there; the remaining exposure is Card Supervisor to the unit component rows and Card Manager to the
  diesel price schedule. Accounting, data and API: no GL, no data change, no new endpoint. Rollback limits: revert
  the commits and migrate; the levels return to 0 and the Card Settings timeline is no longer masked. Card Equipment
  Versions written while the change was live keep the masked component values (nothing to restore; the rows
  themselves are unchanged); Versions written before it keep their raw values.

### Planned
- **Full CARD Mobile** (a later release; design approved 2026-10-19): role-based navigation on real
  permissions; daily operating hours entered by operators, reviewed by supervisors and approved by
  a different manager (separation of duties enforced on the server); equipment, projects,
  assignment, transport, monthly cards, diesel, materials, tools and custody, suppliers, costs and
  reports on the phone; in-app notifications. Accounting documents stay in ERPNext Desk.
- **Ship the native `Sidebar` for fresh 16.50+ installs.** The desk renders `Sidebar` (not the
  deprecated `Workspace Sidebar`). Upgraded sites get the curated Card sidebar via the v1.0.1 fold;
  fresh installs currently get frappe's computed fallback. When the app drops pre‑16.50 support, ship
  the authoritative `Sidebar` file (generated by frappe's `mark_as_standard`, not hand‑encoded) under
  `card/card/sidebar/card/` and remove the now‑inert `Workspace Sidebar` fixture. Kept backward‑safe
  for now because a static `Sidebar` file breaks doc‑sync on pre‑16.50 frappe (doctype absent).
- **Configurable billing basis for the "باليوم" (per‑day) method**, per equipment/contract: the
  current behaviour is **hours‑prorated** — `amount = total_working_hours × (rate / daily_hours)`
  (e.g. 88 h at rate 600 / 10 h‑day → 5,280). Add an option for **full‑day** billing
  (`amount = working_days × rate`). Current behaviour is unchanged until the owner confirms the
  default and the switch.
- **Dated rate agreements** for equipment rates (owner decision 2026-10-19: postponed).

## [4.7.0] — 2026-11-10

Minor release on top of v4.6.0: five pull requests (#199, #200, #201, #202, #203). Security first: company checks on
Employee Tool Custody, Equipment Needs Request and Equipment Needs Review, and `card.tool_custody.move` checks create
before it reads anything (FR-129). New: equipment status guard on project diesel fills (FR-128, Warn only by default),
the read-only Equipment Location History report (FR-130), the role and action matrix with cross-company negative tests
(FR-129). Fixed: the VAT rate of the CARD item tax templates comes from the company's tax templates, no hardcoded 15
(FR-127). Architecture documentation pack (#202). No patch, no DocType schema change; no GL write by CARD. Full page:
[docs/releases/v4.7.0.md](docs/releases/v4.7.0.md).

### Security
- **Company checks on Employee Tool Custody, Equipment Needs Request and Equipment Needs Review** (FR-129, #51, #35,
  #54; PR #203). Reason: a user limited to company A could create records in company B, and with `docstatus` 1 also
  submit them, through `card.tool_custody.move` and `frappe.client.insert`: Frappe checks create/submit on the values
  the client sends (company empty, the user's default company, or any value) and `validate` then set the company from
  the employee, the equipment or the project. A submitted company-B Loss made B's draft Material Issue
  (`_make_stock_entry`, `ignore_permissions`) and changed B's custody balances; a Loss above the balance answered with
  B's balance. Fix: record-level checks on the company the server will set, on every path (read, create, insert with
  `docstatus` 1, save, submit, cancel): `has_custody_permission` (stored company and the companies of `employee` and
  `to_employee`, after the existing delete rule), `needs_request_permission` (stored company and the equipment's
  company, before the operator rule), new `has_review_permission` (stored company and the project's company,
  registered in `hooks.py`); `move` checks create on the new record before it reads anything for the worker.
  Affected: `employee_tool_custody.py`, `card/materials.py`, `equipment_needs_review.py`, `card/hooks.py`,
  `card/tool_custody.py`. Impact: permissions only (deny-only hooks); users without a Company User Permission, or
  with one covering every company, are unaffected; no accounting, data, schema or API change; existing records are
  not changed. Rollback: revert the commit; no patch or data to undo (records created across companies before the
  fix are not detected or changed by it).

### Added
- **Role and action matrix with cross-company negative tests** (FR-129, #51, #35, #54). Reason: one checked record of who
  may do what on every CARD DocType and endpoint, and a guard that no endpoint skips company isolation.
  `docs/governance/ROLE-ACTION-MATRIX.md` lists every CARD DocType (level-0 read, write, create, submit, cancel, delete roles,
  field levels, company mechanism from the DocType JSON and the `has_permission` / `permission_query_conditions` hooks) and
  every `@frappe.whitelist` endpoint (HTTP method, server gate, company isolation, side effects); both tables are rendered from
  `card/tests/test_bola_matrix.py` and a test fails when they drift. The new suite generates, per endpoint (63), a
  cross-company test (a user limited to company A with the endpoint's roles is refused on company B's records, or gets no
  company-B value; nothing is written), a role test (users without the role are refused; nothing is written) and, for read
  endpoints, a no-write test (transaction write counter, row counts and last `modified` of the watched tables unchanged);
  guard tests require every whitelisted function in the table with its decorator's HTTP methods. Four cross-company create
  gaps it found are fixed in the same PR (see Security above) and their tests pass. An allow-list guard requires every `ignore_permissions` site in production
  code to be listed with a reason, and four tests prove that Frappe's company and DocType checks run before the sites
  in `card/transfer.py`, `employee_tool_custody.py`, `card/api.py` `_sync_registry_row` and `card/party_registry.py`
  (a merge rename's `before_rename` writes before Frappe's rename check; the refusal rolls it back). PR #203. Affected (this entry): tests and documentation only;
  the production fix and its impact are under Security. Rollback: revert the commits (no data or schema involved).
- **Equipment status guard on project diesel fills** (FR-128; refs #124, #42). Reason: an ended equipment (status منتهية)
  could still get a new Project Diesel Fill; PR #191 (FR-122) guarded assignments, transports and monthly cards and left
  diesel fills as a TODO. Change: `ProjectDieselFill._check_equipment_status` calls the existing
  `card.equipment_status.check_equipment_status` (new use "diesel fill", one new message
  "Equipment {0} has status {1}; it should get no new diesel fill.") for the direct-charge equipment and every listed
  equipment, with the fill's company and its date as the day. A new fill, or a draft whose company or date changed, checks
  every equipment; otherwise only an equipment added to the draft is checked (compared with the stored fill, as the
  transport does), so an unchanged saved draft is not checked again on save. `before_submit` checks every equipment again;
  the validate of that same submit skips the check, so a warning shows once. An amended copy of a cancelled fill is a new
  fill and is checked: under Refuse, amending a fill whose equipment has ended without an exit date is refused; the
  workaround is to set the equipment's exit date (a fill on or before it is allowed), consistent with FR-122. Another
  company's equipment fails on the company match before its status is read.
  A fill dated on or before the equipment's exit date (else its rental end once passed; the FR-122 `_last_work_day`
  rule) is its last work and is never stopped. Same per-company rule as FR-122: Card Company Settings
  `equipment_status_rule` "Warn only (equipment status)" (the default, also for an empty value or a company without a
  row: a message and the fill is saved) or "Refuse (equipment status)". Only status منتهية stops; Stopped and Under
  Maintenance do not; a project-tank fill without equipment is not checked. Affected: `card/equipment_status.py`
  (`_messages`, docstrings), `project_diesel_fill.py` (`validate`, `before_submit`, `_check_equipment_status`, `_day`),
  locale (one Arabic string); tests `card/tests/test_diesel_fill_status_guard.py`. PR #200. Impact: permissions none; accounting
  none (no GL; submitted fills are never re-validated or changed); data none (no patch, no setting added, existing fills
  unchanged); API: saving a new or changed fill, or submitting a draft, with an ended equipment shows a warning by
  default, or raises a ValidationError when the company chose Refuse. Rollback limits: reverting the commit removes the
  check; nothing is stored by it.
- **Equipment Location History report** (FR-130, #53, #127). Reason: the owner needs to see where each equipment was on
  each period, not only today. New read-only Script Report `Equipment Location History` (roles as the equipment statements and
  Equipment Downtime: System Manager, Card Manager, Card User, Accounts Manager): for one company, an optional equipment and a
  date range, one row per date-aware segment with equipment, from date, to date, location type (Project / Workshop / Storage /
  Supplier / Initial place), location (project title, the transport's place, the equipment supplier of a return to the supplier,
  or the initial place), project, an "Overlapping projects" mark and the source document (Dynamic Link). Segments use the rules
  CARD already applies, from `card.transfer`: a project while a Card Equipment Assignment is in force (`_in_force`), with the
  transport that opened it as source; the assignment dates are those the transport wrote, so the move-day rule recorded on each
  transport (FR-117) is respected and a later change of the company setting does not rewrite history; otherwise the place of
  the last submitted transport on or before the day (as `current_location` does for today); otherwise the company's initial
  place (FR-116, empty when not set). A move to a workshop, storage or supplier on day T shows the project on T and the new
  place from T+1. A unit counts its own assignments and transports on every day and a component's only on the days the
  component is in the unit (`_in_unit_on`); every day is decided from the full history, so a row does not depend on the date
  range, which only clips it (`month_assignments`, used by cards, is unchanged). Two projects in force on the same days get one
  row each, marked, with a report message. Reads are batched: one assignment query, one component query, and per machine only
  its last transport before the range plus those inside it. Company isolation on the server (`resolve_company`; an equipment
  of another company is refused with PermissionError; transports and components of another company are not read); the user's
  roles must read Card Equipment, Card Equipment Assignment and Equipment Transport before anything is read. Added to the CARD
  Reports sidebar. PR #201. Affected: new `card/location_history.py` (`submitted_moves`, `company_segments`, `_History`),
  `card/card/report/equipment_location_history/`, `card/card/sidebar/card_reports/card_reports.json`, locale (the generic
  labels under `msgctxt "Card"`), `card/tests/test_location_history.py`, `card/tests/test_report_access.py`. Impact: permissions
  none (no role widened, no `ignore_permissions`); accounting none (no GL, no document created); data none (read only, no
  patch); API none (no whitelisted method). Known limit: the initial place covers the period before the first move whatever
  the equipment's creation date. Rollback limits: reverting removes the report; the Report and Sidebar records stay on a
  migrated site until removed by hand.

### Fixed
- **VAT rate of the CARD item tax templates from the company's tax templates** (FR-127, #50, PR #199). Reason:
  `ensure_posting_masters` created "CARD VAT 15% - <abbr>" with the rate 15 hardcoded, and the posting preview
  (`_masters_to_provision`) and the preflight (`check_template_mapping`) also expected a hardcoded 15; CARD rules forbid a
  hardcoded VAT rate. One source of truth, no new field: `card.gl.masters.standard_vat_rate(row)` is the single positive
  rate of the company's configured purchase and sales tax templates (Card Company Settings `purchase_tax_template` /
  `sales_tax_template`); a purchase and a sales template with different rates are refused (masters setup, preflight,
  preview block); no configured template gives no rate and no VAT lines, exactly as before; nothing is inferred. The
  item tax template, the posting preview (`_template_vat_rate`), the diesel inclusive net-back and the reconciliation
  (`_vat_rate`) all read this one rate. The rate rows of an existing linked item tax template are never changed
  (ERPNext recalculates `item_tax_rate` from the template on every validate, so changing them would change the VAT of
  old drafts at submit): at the same rate only its accounts are reconciled; at another rate a new "CARD VAT {rate}% -
  <abbr>" template is created and linked in the company row, and the old template stays as it is (not renamed, rates
  unchanged). The 0% template stays 0. The built posting log now also stores the built VAT (each line's
  `item_tax_rate` and `total_taxes_and_charges`, `integrity.vat_snapshot`, outside the signature); the submit gate
  (`check_built_vat`, when the content otherwise matches the built or accepted signature) refuses a draft whose VAT changed since the build; a log written before
  this change has no VAT key and is compared exactly as before. Tests: `card/tests/test_vat_rate_setting.py`. Impact:
  with the 15% templates in use, template names, rates and postings are unchanged. Permissions: none. Schema: none.
  Accounting: a changed company tax template rate gives new drafts the new rate; old drafts keep theirs; a draft whose
  VAT changed between build and submit is refused (rebuild). API: the posting log's `built_snapshot` JSON gains the key
  `vat` for new builds. Rollback: revert the commits; a "CARD VAT {rate}%" template created meanwhile stays (a master,
  harmless) and stays linked in the company row until the row is cleared.

### Documentation
- **Architecture pack** (`docs/architecture/`; #40, #54; PR #202). Reason: the epics ask for a domain map, state transitions,
  source-of-truth matrix, localization matrix, accounting examples, risk register, international test matrix and
  roadmap before any new design is coded. Eight files plus an index, read from the code on `main` @ `8ededce`
  (DocType JSON, controllers, `hooks.py`, `card/gl/`, patches); anything not implemented is marked Planned with its
  issue. The permission matrix is not repeated: it links to `docs/governance/ROLE-ACTION-MATRIX.md`. Documentation
  only: no change to code, permissions, accounting, data or the API. Rollback: revert the commit.

### Migration
- `bench migrate` runs no new patch: `git diff 87c375d be73af2 -- card/patches.txt` is empty.
- Schema: no DocType JSON changed (no new DocType, column or field property). Migrate adds the standard Report
  Equipment Location History and re-imports the Card Reports sidebar (one new link). It writes no GL entry, card
  amount, fill, transport, custody record, tax template or item tax template.
- Read-only pre-deploy check (FR-127, mandatory): for every company, the purchase and the sales tax template of its
  Card Company Settings row each carry exactly one positive rate and both rates are equal (expected 15%). The deploy
  stops if the check fails. Snippet: [docs/releases/v4.7.0.md](docs/releases/v4.7.0.md#124-mandatory-pre-deploy-check-fr-127-read-only).
- Rollback to v4.6.0 (`87c375d`): code only, no data to undo; it re-opens the cross-company gaps fixed by FR-129 and
  removes the diesel-fill status guard and the VAT checks. The `vat` key in new posting logs stays and is ignored by
  v4.6.0 (outside the signature). With 15% templates nothing else differs; a company whose rate is not 15% must not
  build CARD postings on v4.6.0 (it expects 15% and re-rates the linked item tax template). Details:
  [docs/releases/v4.7.0.md](docs/releases/v4.7.0.md#126-rollback-plan).

### Known limitations
- Behaviour changes by default: company-restricted users are refused cross-company custody, needs request and needs
  review records (FR-129); a company with purchase and sales tax templates of different rates, or a template with
  several positive rates, cannot build CARD postings until aligned, and a draft whose VAT changed since the build is
  refused on submit (FR-127). Warn only by default: diesel fills on an ended equipment (FR-128).
- Records created across companies before FR-129 are not detected or changed. FR-127 labels and descriptions that
  mention 15% are kept (backlog). FR-130: the initial place covers the period before the first move whatever the
  equipment's creation date. Details per pull request:
  [docs/releases/v4.7.0.md](docs/releases/v4.7.0.md#10-known-limitations--verified).

## [4.6.0] — 2026-11-10

Minor release on top of v4.5.0: the wave-2 merge train (19 pull requests from #161 to #198; #136, #148, #149, #166
and #204 without user impact). Security: read endpoints GET-only,
diesel fill company isolation, attachment validation, reviewer is not the approver. Governance: mandatory cancel
reason, reviewable period-lock override, dead settings retired. New: configurable stop reasons and the Equipment
Downtime report, effective-dated diesel price schedule, per-company equipment status guard, diesel fill project
check, initial place and move-day rule, other-party transport costs, the CARD Monthly Posting page with a preview,
three read-only analytics reports, card values on the workspace, optional meter extraction. Project-tank diesel posts
at project level. Three data patches; no GL write by CARD. Full page: [docs/releases/v4.6.0.md](docs/releases/v4.6.0.md).

### Added
- **Mandatory cancel reason and a reviewable period-lock override** (FR-123, WP-07, #35, #51, governance G0). Reason: a
  cancelled card, fill or transport had no recorded reason, a cancel request could still change the stored card (FR-050
  open gap 1), and a period-lock override was only in the server log. Card Monthly Card, Equipment Transport and Project
  Diesel Fill get `cancel_reason` (Small Text, no copy, read only; not "allow on submit": a cancel stores it without
  Frappe's update-after-submit check, so no update-after-submit path is opened). The form's Cancel asks for the reason
  and cancels through `card.cancel_reason.cancel_with_reason` (POST; one request, so a refused cancel keeps no reason).
  `before_cancel` refuses a cancel without a reason on every path (Desk, REST `docstatus` 2, Python/API) and refuses a
  cancel request that changes any other stored field or child row; `on_cancel` adds an Info Comment with the actor, the
  reason and the date. A save or submit drops a copied reason; an update after submit cannot set it. A period-lock override
  (`card.period_lock`) now also adds an Info Comment on the stored document (actor, action, date, lock date) next to the
  existing log. PR #197. Affected: `card/cancel_reason.py` (new), `card/period_lock.py` (`_log_override`,
  `_comment_override`), `card/hooks.py` (doc_events of the three doctypes, `doctype_js`), `card/public/js/cancel_reason.js`
  (new), the three DocType JSON files, `card/locale/ar.po`, `main.pot`. Permissions: none widened; the cancel uses Frappe's
  cancel permission and the doctypes' company has_permission hooks; Workflow and roles unchanged. Accounting: none (no GL
  entry, no posting change). Data: one new column per doctype; existing records untouched (records cancelled earlier keep
  an empty reason; no patch). API: a cancel without `cancel_reason` is now refused for these three doctypes, including
  Frappe's "cancel all linked documents". Rollback limits: code revert only; the added columns stay (harmless) and the
  stored reasons and comments remain.
  Review fixes (PR #197): the reason is stored as plain text (HTML tags and any left `<` `>` removed in
  `before_cancel`, because Frappe skips `_validate`/`_sanitize_content` on cancel; a reason that is only markup is
  refused); the change check has no default-value tolerance (Frappe fills defaults only for new documents and new
  rows). Known limits: an active Workflow's cancel action (`apply_workflow` -> `doc.cancel`) cannot send a reason, so
  it is refused (the Card Monthly Card workflow is inactive on Production today); the List view bulk cancel
  (`submit_cancel_or_update_docs`, a background job above 20 records) is refused too: cancel each record from its
  form with a reason.
- **Configurable stop reasons, the responsible party of a stopped day and the Equipment Downtime report** (FR-118,
  WP-09, refs #45 #123, PR #194).
  - **Reason:** #45 (owner decision): record why, how long and because of whom equipment stood still, from a
    configurable per-company catalogue, with **no rental for stopped periods unless explicitly configured**; #123 asks
    for a downtime report.
  - **Change:** new master DocType **Card Stop Reason** (`company` mandatory, `reason_name`, `enabled`, `billable`
    default off, optional `default_responsible_party_type`, `day_status` it matches, notes; named
    "<reason> - <company abbr>", unique per company; `track_changes` on; written by System Manager and Card Manager,
    read by Card User, Card Supervisor and Accounts Manager; Company User Permissions apply through its `company`
    link). Card Monthly Card Day gets `stop_reason` (Link, the form offers only enabled reasons of the card's company),
    `stopped_hours`, `reason_billable` (read-only snapshot of the reason's flag), `responsible_party_type`
    (Company / Supplier / Customer / Other), `responsible_party` (Dynamic Link) and `responsible_party_name` (Other).
    Card Monthly Card gets `billable_stopped_hours` (read-only). `CardMonthlyCard._resolve_stop_reasons` refuses a
    reason of another company, a missing or a disabled reason, takes the reason's default responsible party, sets a
    Company party to the card's company (another company is refused) and clears the fields that do not fit the type.
    Only the stopped hours of a row whose reason is billable are added to the billed hours of both sides
    (`amount`, `customer_amount`); `total_working_hours` and `working_days` stay operating figures. A billable
    stopped day must fall inside the assignment period and outside a unit-component period like a working day
    (`card.transfer.is_billed_day`, used by `validate_card_days` and `_refuse_unit_component_days`); stopped hours on a
    future day are refused. New read-only Script Report **Equipment Downtime** (`card/card/report/equipment_downtime`):
    stopped days, full stopped days, stopped hours and billable stopped hours by stop reason, responsible party,
    equipment, project, month or each day; one company through `card.report_access.resolve_company`, the cards the
    user may read through `frappe.get_list`, submitted cards (drafts on request); rows of older cards without a
    reason are shown under their day status. Added to the Card Reports sidebar. Patch
    `card.patches.v4_6_0.seed_stop_reasons` (post_model_sync) creates, for each company that has cards, one reason
    per non-working day status (إجازة, عطل, توقف من العميل) with billable off. The seed covers only the companies
    that have cards when `bench migrate` runs; a company that gets its first card later creates its reasons by hand.
  - **Review of PR #194:** the day queries that keep a submitted card day inside its assignment
    (`card.transfer._card_day_after`, `card_equipment_assignment._refuse_dropped_card_days`) and the cost-centre day
    choice of a CARD posting (`card.gl.posting.card_cost_center`) count a billable stopped day as a billed day;
    operating plus stopped hours over 24 on one day are refused (a day without stopped hours keeps the old rule);
    billable stopped hours count in the advisory shift-limit warning; a Supplier or Customer held responsible that
    is not the card's own gets a review warning (never a block); the internal value of an owned card
    (`card.card_value`) counts billable stopped hours (per hour) and billable stopped days (per day). The Equipment Supplier/Customer Statements and the two
    summaries count a billable stopped day in the days (`card.transfer.billed_day_rows`) and show a "Billable
    stopped hours" column with its totals only when a row has a value (`with_stopped_hours_column`; the approved
    print adds the column the same way, `statement_pdf._with_stopped_hours`, so a statement without billable stops
    prints exactly as before; the standard Print Format "Equipment Supplier Statement A4" ships the same template). Hourly rate: the
    supplier statement shows each card's amount over operating plus billable stopped hours (with no billable stop:
    amount / operating hours, exactly as before); the customer statement keeps the submit-time rate
    (`customer_rate_used`) for submitted cards and uses amount over operating plus billable stopped hours for
    drafts. The internal value per day (`card.card_value`) also counts the days billed only by billable stopped
    hours (new read-only card field `billable_stopped_days`).
  - **Defaults (no behaviour change):** a card without reasons bills exactly as before, every seeded and new reason
    is not billable, the four fixed day statuses and their effect (a non-working status zeroes the operating hours)
    are unchanged, and the patch writes no card or day row. `min_hours` is still not read (FR-020 stays an open owner
    decision).
  - **Impact:** permissions: one new master with the roles above, no role widened, no `ignore_permissions` in
    production code. Accounting: none by default; once a Card Manager ticks `billable` on a reason, the card amounts
    (and so the CARD postings built from them) include those stopped hours. Data: new table and new columns; the
    patch inserts reasons only. API: no new whitelisted method. No statement, summary or dashboard figure
    changes for cards without billable stops.
  - **Rollback:** revert the PR; the new columns and the Card Stop Reason table and rows stay in the database
    (harmless, unread). Cards saved with a billable reason keep their amounts until they are saved again (drafts) or
    amended (submitted).
- **Effective-dated diesel price schedule** (FR-125, #46, #124 WP-10). Reason: the diesel price changes over time and a fill
  must take the price valid on its own date. Card Settings > Diesel Settings gets the table **Diesel price schedule** (new child
  DocType `Card Diesel Price`: company, valid from, price per litre, currency defaulting to and limited to the company currency,
  optional UOM; level 1 like `diesel_unit_price`). It lives on Card Settings with a company column because Card Company Settings is
  itself a child table and Frappe has no nested child tables. A fill takes the price of its company's row with the latest valid
  from on or before the fill date; with no such row (no schedule, or a date before the first row) it takes `diesel_unit_price`
  exactly as before. Validation: one price per company and date, a required price above zero, company scope as for the other
  company rows. **Behaviour change (review M1):** once a company has schedule rows (after the seed patch: every priced company),
  its `diesel_unit_price` is read-only on the form and the server refuses a change; its price changes only by a new dated schedule
  row. A saved Company Price draft whose date moves to a period with another price goes to Needs Review (like a company change);
  it is never repriced silently. Known limit (review M3, the same gap main has for `company_settings`): Card Settings is a Single,
  so a user who can read level 1 receives the schedule rows of every company; the form shows the price box only for permitted
  companies and the server refuses changes to other companies' rows, but the rows are not stripped from the loaded document
  (stripping them would delete them on the next save).
  A new or changed row dated on or before submitted fills does not change them; the user is told how many submitted fills of the
  company are on or after that date. The Diesel Settings price box shows today's price and, for a company with a schedule,
  "Change price" adds a dated row. Patch `v4_7_0.seed_diesel_price_schedule` (post_model_sync, idempotent) gives each company with
  `diesel_unit_price` > 0 and no schedule one row with that price, valid from its earliest fill date (today without fills);
  `diesel_unit_price` is not changed. PR #195. Affected:
  `project_diesel_fill.py` (`scheduled_diesel_price`, `diesel_price(company, on_date)`, `get_diesel_price_context` gains `date`,
  `_apply_price`), `project_diesel_fill.js` (price on the fill date), `diesel_import.py` `_check_price` (session date),
  `card_settings.py` (`_validate_diesel_price_schedule`, `COMPANY_TABLES`), `card_settings.js`, `card_settings.json`, locale.
  Impact: permissions none (same level 1 as the price; no role widened); accounting none (no GL; the fill amount is litres x the
  price as before); data: one schedule row per priced company after migrate, no fill changed; API: `get_diesel_price_context`
  accepts an optional `date` (GET, read only). Rollback limits: reverting the code leaves the `Card Diesel Price` table and the
  seeded rows in the database (unused); fills saved while the schedule was active keep the price they took.
- **Diesel fill project check** (FR-126, #124 WP-11, #31). Reason: diesel charged to an equipment that is not on the fill's
  project puts the cost on the wrong project. A fill's direct-charge equipment and every listed equipment need a Card Equipment
  Assignment on the fill's project in force on the fill date, by the rule of `card.transfer._in_force` (a from date on or before
  the day, an empty or later to date; an assignment without a from date covers no day; the status field is not read, as in
  `_in_force`). On the day of a project-to-project move the fill goes to the project the company's move-day rule (FR-117) gives
  that day: the old project under "the day after the move", the new project under "on the move day". New Card Company Settings
  Select `diesel_fill_project_check` (level 1) with CARD-specific values: "Off (diesel project check)", "Warn only (diesel project
  check)" (default; an empty value also means Warn only: a message and the fill is saved) or "Refuse (diesel project check)".
  Only a new fill, or a fill whose company, equipment, project or date changed, is checked; submitted fills never reach validate
  and an unchanged draft submits as before. PR #196. Affected: `project_diesel_fill.py` (`ProjectDieselFill._check_equipment_on_project`,
  `equipment_on_project`, `_filled_equipment_of`), `card_company_settings.json`, locale. Impact: permissions none; accounting
  none (no GL; nothing reposted); data none (no patch, no fill changed); API none. Default: Warn, so existing work only sees a
  message. The equipment-status guard for diesel fills (TODO of PR #191) is not included; it is a follow-up (FR-128,
  PR #200, not in 4.6.0). Rollback limits: reverting removes the check; the stored setting value stays unused in the
  database.
- **Equipment status guard** (FR-122, PR #191; refs #42, #120).
  - **Reason:** the Card Equipment status was a plain field: an ended machine (status منتهية) could still get a new
    assignment, transport or monthly card.
  - **Change:** new `card/equipment_status.py` (`check_equipment_status`, `status_rule`) called from
    `CardEquipmentAssignment.validate`, `EquipmentTransport._check_equipment_status` (on save and again in
    `before_submit`) and `CardMonthlyCard.before_validate` (after the company match, so another company's status is
    never shown). An assignment or card is checked when it is new or its equipment changes (compared with the stored
    value). A transport is checked on save for a new transport, a changed destination or project (every machine) or
    an added machine, and on submit for every machine, so a draft saved while the machine was active, or switched
    from a supplier return to a project, is checked before it applies. New Card Company Settings field
    `equipment_status_rule` (permission level 1) with the stored values "Warn only (equipment status)" (the default,
    also for an empty value or a company without a row: message, then save) and "Refuse (equipment status)"
    (refused). Only status منتهية (Ended) stops new use; متوقفة (Stopped) and في الصيانة (Under Maintenance) stay
    allowed. Never stopped: a return to the supplier (end of a rental), a move of an owned machine to storage or a
    workshop (how it is retired), and a monthly card whose period starts on or before the equipment's exit date
    (else its rental end once it has passed; a contract end still ahead gives no allowance), so the final
    partial month is carded; without such a date every new card is checked.
    The assignment a transport creates is not checked again (`card_from_transport` flag in `card/transfer.py`).
    Project Diesel Fill is not guarded in this change.
  - **Impact:** permissions — none (the setting is level 1 like the other company fields). Accounting — none.
    Data — none: existing records are never changed; nothing is refused until a company chooses Refuse. API —
    saving a new assignment, transport or card, or submitting a transport, of an ended machine shows a warning, or
    raises a ValidationError under Refuse. Eight new Arabic strings.
  - **Rollback:** revert the commit; an older version ignores the new column.
- **Transport costs the company does not pay, and an "other party" responsibility** (FR-120, refs #43, #48, #121;
  WP-14; PR #190).
  - **Reason:** when the equipment supplier, the customer or another party pays a move, the amount agreed with
    them was lost (the transporter cost is 0 for these moves), and a party other than the supplier or the customer
    could not be recorded.
  - **Change:** Equipment Transport gets the responsibility **Other party bears the cost** (payer and cost bearer
    `Other Party`) with the party named in `party_type` (Supplier, Customer or Employee) and `party` (Dynamic
    Link, label "Other party bearing the transport cost"); an employee must be an active employee of the
    transport's company (the message never names another company), a missing or disabled party is refused. New optional
    Currency `informational_amount` ("Agreed amount (not company cost)") on moves the equipment supplier, the
    customer or the other party pays; every other move keeps 0 and no party. Affected functions:
    `EquipmentTransport._apply_other_party`, `_apply_informational_amount`, `_cancel_key` (a cancel cannot rewrite
    the new fields); `card.transport_costs.not_company_cost_project` and `not_company_cost_by_project`; the reports
    Transport Cost by Project (columns "Transports not paid by the company" and "Agreed amount (not company cost)"),
    Operating Cost by Project (column "Agreed amount (not company cost)", not in the total) and Transport Accounting
    Review (columns "Agreed amount (not company cost)" and "Other party bearing the transport cost"). New constants
    in `card/constants.py`.
  - **Impact:** permissions: none (no role, no permission change; the fields are level 0 like the transporter
    cost). Picking an Employee party on the form needs Employee read permission (no role is widened for it); the
    server-side company check is what enforces the scope. Accounting: none: the amount is never company cost, never in the partial margin and never posted (the
    P1-2 posting exclusion of transports with a responsibility is kept). Data: three new nullable/zero columns on
    Equipment Transport, new Select options; no patch, existing transports unchanged. API: the new fields are
    accepted on save; a client that sends payer and bearer `Other Party` gets the new scenario.
  - **Rollback:** revert the commit. The added columns stay in the database (Frappe does not drop them) and are
    then unused; a transport submitted with "Other party bears the cost" keeps that stored value, which an older
    version counts as a move the company does not pay in its reports but refuses on a new save (unknown
    responsibility); amend such transports before a rollback.
- **CARD Monthly Posting page with a posting preview** (FR-119, refs #49 #126; PR #193, branch
  `feat/posting-preview-49`).
  - **Reason:** accountants built the month-end drafts blind: `post_month` / `rebuild_month` had no Desk screen and
    no way to see the lines before a draft Purchase / Sales Invoice was created and its sources reserved.
  - **Change:** new Desk page `card-monthly-posting` (roles Card Manager and System Manager, the roles the build
    endpoints already require). Pick a company and a month; the page lists each supplier and customer with its status
    (Not posted / Draft / Posted), the documents not yet in a posting and its CARD postings; **Preview lines** shows the
    lines the next draft (or the rebuild of the current draft) would carry — item, account, amount, project, cost
    center, equipment, taxable / zero-rated and item tax template per line, totals, discount, an estimated VAT, the
    diesel VAT-basis note and the source documents — and the supplier invoices an accountant must review first
    (tickable only by Accounts Manager / Accounts User / System Manager, as before). **Create draft posting** /
    **Rebuild draft posting** call the existing `card.gl.posting.post_month` / `rebuild_month` unchanged.
  - **Affected functions:** `card.gl.posting.build_monthly_posting` is split into `_plan_monthly_posting` (all gates and
    lines; `dry_run=True` skips `ensure_posting_masters`, `integrity.lock_sources` and the reviewed-invoice refusal and
    returns the candidates instead) and the unchanged insert/log/reserve part; the item row is built by the shared
    `_invoice_item`; `rebuild_monthly_posting` reads its drafts through `_rebuildable_drafts`;
    `_held_by_active_log` / `_exclude_held` take an optional `ignore_logs` (rebuild preview only);
    `_supplier_sources` / `_customer_cards` accept `party=None` (party list);
    `card.gl.preflight.check_template_mapping` takes `provisioned=True` (default unchanged; a preview before the
    first post skips only the CARD item tax template rows, every other tax check still refuses). New:
    `preview_monthly_posting`, `month_parties` (batched hold lookup `_unheld_batch`), whitelisted `preview_month` and `posting_month_parties` (both `methods=["GET"]`, side-effect
    free, same role, company and party gates as `post_month`).
  - **Impact:** permissions — none changed; GL Posting Log stays readable by System Manager, Accounts Manager and Card
    Manager (Accounts User read is an open owner decision). Accounting — none: the real build runs the same steps in
    the same order with the same amounts; the preview writes nothing (tests patch every write path). Data — none, no
    schema change, no patch. API — two new GET methods.
  - **Rollback:** revert the commit; nothing is stored by the page or the preview.
- **Meter extraction inside the existing Diesel Fill** (FR-101, Owner decision 2026-11-02; no new DocType, field or table).
  An optional LOCAL worker (`card_meter_worker_url` / `card_meter_worker_token` in site_config; absent = nothing changes) reads the
  opening and closing meter photos after they are saved. CARD validates every byte the worker returns, crops the counter itself
  (private File + one Comment per pass) and decides inside the fill's own validation: when both photos are clear (every drum read,
  opening zero, closing above opening, the entered litres equal the reading) the closing reading is written and the fill stays a Draft
  (never submitted, never posted); any `?` / half-rolled / unreadable drum or defect writes NO reading and records the disputed reading
  (`Meter reading (closing): 0004? ...`) in `evidence_warnings`. Owner rule 2026-11-03: only a clear, validated reading stays a Draft; every other processed outcome (an unreadable
  or ambiguous side, no meter, a conflict, a clear reading that was not written) routes the fill to Needs Review with a visible line. A machine-written closing keeps an informational
  line in `evidence_warnings` (`written by meter extraction; check against the photo`) so it is not mistaken for a typed number; it never routes. A person's reading or litres is never overwritten, approved/rejected/submitted fills are never touched, the same
  photo bytes are processed once, and the job runs as the user who saved the photo. Expect most real photos to need a person until the
  engine is validated on verified labels. Invoice litres, litres quoted in the source messages and the totalizer can only ESCALATE a
  clear reading (it is then not written and the fill goes to Needs Review); they never verify one. A person-entered opening reading
  that disagrees with the photo blocks the write, so the entered litres never change. Audit markers are signed with the site secret
  and a user-typed Comment is ignored; the worker's engine name/version must match a strict character set, its interval is
  recomputed from the drums, requests ignore proxy environment variables, jobs for one fill run one at a time, and busy or
  unreachable answers are retried later instead of counting toward the three-attempt cap. A drum-count difference between the two
  photos is recorded but is not by itself a reason for Needs Review. The crop is refused only for a box over 60% of the image area or
  height (a close-up meter is a wide box and is cropped), and the Desk shows the disputed reading as an isolated left-to-right text, so
  its brackets and `?` keep their order inside an Arabic sentence. A full background queue or an
  unreachable Redis never fails the save: the extraction is skipped for that save, an Error Log row is written and the photo stays
  manual (no retry). PR #164; uses the attachment validator of PR #162 (FR-099, merged). Affected: `card/diesel_meter_extraction.py` (new), `ProjectDieselFill.validate`
  (`_apply_meter_extraction`, `_totalizer_window`), `project_diesel_fill.js`, `hooks.py` (`on_update` of Project Diesel
  Fill), `card/locale/ar.po`. Impact: permissions none (the job runs as the saving user, no `ignore_permissions`); accounting
  none (nothing submitted or posted); data: with the worker configured, a Draft's `closing_reading`, `review_status` and
  `evidence_warnings` may change, and private crop Files and Info Comments are added; API none (no whitelisted method);
  no schema change, no patch, no new Python dependency (`requests` and Pillow come with Frappe). With the worker off
  (the default) no photo bytes leave the site. Worker address (Owner decision 2026-11-10, review finding: a host name
  was resolved for the check and again by the request, so a changed DNS answer could send the photo elsewhere):
  `card_meter_worker_url` must use an IP literal host, `http` only to a loopback address (`127.0.0.1`, `[::1]`),
  `https` only to a loopback or private address (IPv6: only `::1` and unique local `fc00::/7`; 6to4 `2002::/16` and
  Teredo `2001::/32` refused; an IPv4-mapped IPv6 address is judged as IPv4); nothing is resolved.
  A host name (including `localhost`), a public, link-local or unspecified address is refused: the job stops before any
  photo is read (no attempt is counted) and one translated Error Log per reason and day says why, without the URL. A
  site that set a host name must change it to the IP address (for `https`, the worker's certificate must then name that
  IP). Rollback: remove the two site_config keys (feature off at once) or
  revert the commits; crops and markers already written stay as ordinary attachments and comments.
- **Governance inventories (documentation only; PR #186; refs #40, #50, #52, #54).**
  `docs/governance/SETTINGS-AND-CONSTANTS.md` lists every Card Settings and Card Company Settings field with its
  readers (file:line), the code defaults and inline fallbacks, the precedence document → Card Company Settings →
  Card Settings → code default, the four dead settings of FR-015 and the hardcoded values that affect behaviour
  (WP-18). `docs/governance/INTAKE-PROVENANCE-DESIGN.md` is a design, not implemented, for source keys, evidence
  hashes, idempotency, review and permissions of movement and operation intake (WP-21).
  `docs/governance/HRMS-PARITY.md` compares the CARD equipment model with the Frappe HR employee model (official
  HRMS `version-16` source and docs.frappe.io/hr only) and records the upgrade-rehearsal CI evidence. Impact on
  permissions, accounting, data and the API: none. Rollback: revert the commit.
- **Every monthly card shows its value on the CARD workspace** (FR-111, PR #185, owner requirement
  2026-11-10).
  - **Reason:** the chart "مبالغ الكروت الشهرية" and the number card "مبالغ الشهر الماضي" summed only the supplier
    `amount`, which is 0 for owned and managed equipment; a month with only owned cards (for example an owned crusher
    rented to a customer) looked empty.
  - **Change:** new module `card.card_value` and Dashboard Chart Source **Card Monthly Values**
    (`card/card/dashboard_chart_source/card_monthly_values/`). Per submitted card: supplier side (`مستأجَرة من مورد`,
    `إيجار من الباطن`) → `net_amount`; customer side (`مؤجَّرة لعميل`, `إيجار من الباطن`) → `customer_net_amount`;
    owned or managed equipment (`ملك`, `طرف ثالث`) with an internal rate → hours × rate, or working days × rate when the
    basis is per day. Each value is its own series and is never added to another. A card with no supplier or customer
    side and no internal rate still counts: number cards show how many such cards and how many hours last month.
    New Card Equipment fields `internal_rate_basis` (Select `بالساعة`/`باليوم`, default per hour) and `internal_rate`
    (Currency), level 2 like `internal_hourly_rate`, in the "Internal cost" section, which now also shows for managed
    (`طرف ثالث`) equipment; both are commercial terms (a change needs a reason). An equipment with only the older
    `internal_hourly_rate` is valued per hour with it. The chart filter "Include draft cards" is off by default, as the
    old chart (submitted cards only).
  - **Fixtures:** the chart "مبالغ الكروت الشهرية" becomes a Custom chart on that source (three series per month:
    "تكلفة إيجار من موردين", "قيمة تشغيل لعملاء", "قيمة تشغيل داخلي"); the number card "مبالغ الشهر الماضي" (name kept)
    becomes a Custom card for last month's supplier cost (label "تكلفة إيجار من موردين - الشهر الماضي", now
    `net_amount` with additions and deductions, it was `amount`); four new Custom number cards (customer value,
    internal value, "كروت بدون سعر داخلي", hours without an internal rate) are added to the Card workspace.
  - **Permissions:** none widened. Reads use `frappe.get_list`, so the Card Monthly Card read right and Company User
    Permissions apply (no hard-coded company; the optional company filter cannot widen them). The internal series and
    the two missing-rate cards need read access to the level-2 rate fields (System Manager, Card Manager, Accounts
    Manager); other users get the supplier and customer series only and "N/A" on those cards. The source is not
    cached (Frappe's `cache_source` key is per chart, not per user). The chart and the five number-card methods are
    side-effect-free reads declared `methods=["POST"]` because Frappe's dashboard widgets call them with
    `frappe.xcall`, which always sends POST.
  - **Accounting:** none. No document or GL entry is created or changed; the internal value is for display only.
  - **Data / schema:** two new nullable columns on `tabCard Equipment`; no patch (the fixtures overwrite the chart,
    number cards and workspace on `migrate`, as before). **API:** five new POST methods in `card.card_value` and the
    source method `card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get`.
  - **Rollback:** older code ignores the two new columns (they stay, with their values). Its fixtures restore the old
    Sum chart, number card and workspace on its next `migrate`; the four new number cards and the Dashboard Chart
    Source stay in the database, off the workspace, until removed by hand (their methods no longer exist there).
- **Analytics reports: Equipment Partial Margin, Unbilled Card Work, Equipment Maintenance Cost** (#53, #127 P8;
  audit work packages WP-16 and WP-17; FR-112, FR-113, FR-114; PR #188).
  - **Reason:** #53 and the go-live phase P8 (#127) ask for equipment profitability, unbilled work and a maintenance
    report; none existed.
  - **Change:** three read-only Script Reports in the CARD Reports sidebar, all for one company (mandatory filter,
    validated with `card.report_access.resolve_company`) and one period; shared reading helpers in the new module
    `card.analytics`.
    - **Equipment Partial Margin** (System Manager, Accounts Manager; General Ledger access required,
      `can_view_ledger`): per equipment and project, revenue from submitted Sales Invoice lines carrying the Card
      Equipment accounting dimension (net of VAT, company currency, credit notes included); the customer net of
      submitted cards no submitted document recognised yet, in a separate "not invoiced yet" column that is never
      added to revenue or the margin; supplier rental as recognised by submitted documents (CARD purchase invoices,
      linked invoices, accrual journal entries linked with `card.gl.journal_link`), with the supplier net not yet
      recognised shown apart and not added to costs; diesel of direct fills at the posting's valuation (the net booked
      on a submitted CARD posting; a fill not posted yet is converted to net by the posting's own rule,
      `card.gl.posting._apply_diesel_vat_basis`, and kept at its amount with a message where the diesel VAT basis is
      not verified); project-tank fills are not split by equipment and stay
      on a project-level line "unallocated tank diesel" (#118 rule 7); company-borne transport by its recorded
      equipment shares (same rule as `card.transport_costs`); maintenance and other costs tagged with the dimension.
      Labelled "partial margin: excludes depreciation, labour, insurance and overhead". The message states the timing:
      revenue and maintenance by document posting date, rental and the not-invoiced columns by the card's start date.
    - **Unbilled Card Work** (System Manager, Accounts Manager, Card Manager; the user's roles must read the GL Posting
      Log): submitted cards, supplier side and customer side apart, that no active GL Posting Log and no invoice link
      of that side holds; optionally the cards held by a draft posting.
    - **Equipment Maintenance Cost** (System Manager, Accounts Manager; General Ledger access required): submitted
      Purchase Invoice lines and Material Issue Stock Entry lines tagged with the Card Equipment dimension. Invoices
      that recognise CARD cards, diesel fills or transports (and their returns), fixed-asset lines and lines of stock
      items are left out (a stock item reaches the equipment through its material issue; counting the purchase too
      would count it twice).
    - Without the Card Equipment dimension (FR-031) the margin shows a clear message and leaves revenue and maintenance
      out; the maintenance report shows the message and no rows. Nothing fails.
  - **Changed (no behaviour change):** `card.transport_costs` exposes its company-cost rule as
    `company_cost_project(row)` and `TRANSPORT_COST_FIELDS`; `transport_cost_by_project` uses them.
    `card.report_access.role_reads(doctype)` is a public name for the existing role-read check.
  - **Affected:** new `card/analytics.py`; new reports `equipment_partial_margin`, `unbilled_card_work`,
    `equipment_maintenance_cost`; `card/transport_costs.py`; `card/report_access.py`; Sidebar "Card Reports"
    (three links; file `modified` bumped so migrate imports it); `card/locale/ar.po`, `card/locale/main.pot`;
    tests `test_analytics_reports.py` (20), `test_report_access.py` (filter check covers the new reports).
  - **Impact:** permissions — none widened: the reports read business documents with `frappe.get_list` (the user's
    permissions and User Permissions apply), child rows only of the parents returned, and the GL Posting Log only
    after the server-side role gate. Accounting — none: nothing is posted, created or changed; no GL write. Data —
    none written. Schema — none (three Report records and the sidebar rows are created by migrate). API — no new
    whitelisted method.
  - **Rollback:** code-only. Reverting removes the reports from the code; migrate does not delete the three Report
    records it created (delete them by hand if wanted). No data to restore.
- **A combined unit is owned equipment only** (#42, WP-04; FR-115; PR #187).
  - **Reason:** owner requirement in #42: the "two machines together" option is available only for owned equipment,
    in the UI and the backend, including ownership changes and existing records.
  - **Change:** `card_equipment.py` `validate_owned_unit` and `check_unit_components` refuse a rented (or third-party)
    equipment that becomes a unit, a unit or a listed component whose ownership changes away from owned, a piece that
    is not owned joining a unit, and any piece joining a unit that is not owned. The same rules cover the form, REST,
    `frappe.client`, a component row saved on its own and `replace_component` / `move_component`. Existing records are
    not blocked by an unrelated save and are never changed: `get_unit_integrity_issues` (`methods=["GET"]`, Card
    Equipment read, the user's Company User Permissions apply) lists them, and a piece of a legacy rented unit can
    still be taken out. The components grid and the unit actions offer only owned, non-unit equipment of the unit's
    company; the unit tick is read-only on equipment that is not owned.
  - **Impact:** permissions — none widened. Accounting — none. Data — none written. API — one new GET method.
  - **Rollback:** code only; nothing to undo in data.
- **Initial place of new equipment per company** (#42, WP-06; FR-116; PR #187). New field `initial_location` (Location) in
  Card Settings > Company settings. `card.transfer.current_location` returns it as the storage place of any equipment
  with no movement history (no assignment and no approved transport; this includes an existing equipment never moved,
  not only a new one), so the first transport shows it as From (row `from_location`,
  header `source_location`) and a move to that same place is refused as "already there". No place is hardcoded; empty
  (the default) keeps "storage without a place", as before.
  - **Impact:** permissions — the field is permission level 1 of Card Settings (Accounts Manager, System Manager
    write), like the other company fields. Accounting, data, API — none.
  - **Rollback:** code and schema; an older version ignores the column.

### Changed
- **Dead settings retired, not deleted** (FR-124, WP-08, FR-015, #50). Reason: four settings had no reader, so changing
  them did nothing. `auto_submit` and `notify_on_posting` (Card Settings) and `bank_cash_account` and `mode_of_payment`
  (Card Company Settings) are now hidden and read only with the description "Deprecated – not used" (Arabic in
  `card/locale/ar.po`); the two Card Settings entries are removed from `settings.py` `_DEFAULTS`. No reader was found for
  any of the four, so none was wired up. The account-company check of `CardSettings.validate` skips a retired (hidden,
  read only) account field, so an old value of another company stored there cannot block saving Card Settings while
  nobody can see the field to clear it. PR #198. Affected: `card_settings.json`, `card_company_settings.json`,
  `card_settings.py` (`validate`),
  `card/settings.py`, `docs/governance/SETTINGS-AND-CONSTANTS.md`; test `test_deprecated_settings.py` (fields hidden,
  no reader in the app code). Permissions: none changed (same permlevels). Accounting: none. Data: columns and stored
  values kept; no patch. API: the fields stay in the DocType and API reads; a write through the API is still stored but
  has no effect, as before. Rollback limits: code revert only (the fields show again).
- **CI: upgrade rehearsal on the current Production platform** (PR #192; refs #119, #120). The rehearsal now runs on
  frappe `v16.55.2` / erpnext `v16.54.0` (the Production platform of 2026-11-10; tags checked on GitHub) instead of
  16.51.1 / 16.50.0, and on every pull request: the path filter is removed because the job takes about 5 minutes
  and runs in parallel with the CARD unit tests (about 10-16 minutes), so no pull request waits longer, and Python
  code that migrate runs is rehearsed too. Files: `.github/workflows/upgrade-rehearsal.yml`,
  `.github/helper/upgrade_rehearsal.sh`, `docs/governance/HRMS-PARITY.md`. HRMS stays off the rehearsal site (CARD
  depends on frappe and erpnext only). Impact on permissions, accounting, data and the API: none. Rollback: revert
  the commit.
- **Project-tank diesel posts at project level** (D1, FR-100, Owner direction 2026-11-02). A Project Diesel Fill
  without equipment is now ONE Purchase Invoice line (its full amount, the project, no equipment) instead of one
  line per equipment split by operating hours; an hours-based split is an estimate, not a posting basis. Its cost
  center is the fill's own, else the project's (no assignment of any equipment; "Cost allocation needs review" when
  neither is usable). Direct fills (with equipment) are unchanged. The line description no longer says "estimated
  share". The GL equipment dimension therefore no longer includes tank diesel. Diesel reports and
  `get_card_diesel` keep their labelled estimates and are unchanged; the PI-item-based Equipment Consumption no
  longer includes tank diesel per equipment, while the Estimated reports still show the labelled estimate. The
  "Equipment Expenses Without Equipment" guard report no longer lists project-tank diesel lines (identified through
  the fill that points to the invoice) and counts them in a separate tile. Submitted invoices and posting logs are not
  touched. Tank diesel's cost center moves from the equipment assignment's to the fill's own or the project's, so
  cost-center and equipment-dimension reports around the release are not month-to-month comparable.
  **Rebuild open draft postings built before this release before submitting them.** Enforced (Owner decision
  2026-11-10): the builder now records its version (`"builder": 2`) in the GL Posting Log's `built_snapshot` JSON
  (not in the signature hash, so other drafts still match); `card.gl.integrity.check_built_signature` refuses the
  submit of a draft built by an earlier builder when it holds a project-tank fill ("Rebuild the posting from CARD
  before submitting it", Arabic translation in `ar.po`), also when an Accounts Manager accepted a correction on it.
  A pre-change draft without a project-tank fill submits as before. PR #163. Affected: `card/gl/posting.py`
  (`build_monthly_posting`, diesel loop, `fill_line_cost_center`), `card/gl/integrity.py` (`BUILDER_VERSION`,
  `stored_snapshot`, `check_builder_version`), guard report `equipment_expenses_without_equipment.py`. Impact:
  permissions none; accounting: the distribution of tank diesel moves to the project line (totals unchanged; no GL
  write by CARD); data: no patch, no schema change, existing logs and submitted invoices untouched; API none.
  Rollback: revert the commits; drafts built by the new builder keep one project-level tank line and the old code
  submits them as they are (rebuild them to get the old split).
- **Feature registry corrected (documentation only).** FR-073, FR-074, FR-075 (v4.1.0), FR-085, FR-086, FR-086b
  (v4.2.0), FR-087 (v4.2.1) and FR-088 (v4.2.2) were still *In review* / *In development* although merged and
  released; they are now Implemented with their pull requests, merge commits and releases. FR-038 names the
  transport cost-center checks of FR-091 and FR-093. Rows released in v4.3.0 to v4.4.3 no longer say "not
  deployed" (deployed 2026-11-09 per `DEPLOYMENTS.md`); v4.5.0 is released, not deployed.
  No row deleted. Impact: none. Rollback: revert the commit.
- **Move-day rule of a project → project transport, per company** (#43, #121, #122; WP-15; FR-117; PR #187). Owner wording in
  #43: "one effective date equal to arrival date" and "approval makes destination effective on arrival/effective
  date"; the open decision on #121/#122/#43: "on a project → project move, which project gets the move day?".
  - **Change:** new field `move_day_rule` in Card Settings > Company settings: "New assignment starts the day after the
    move" (default, the rule CARD always applied: the old project keeps the move day) or "New assignment starts on the
    move day" (the move day goes to the new project; the old assignment ends the day before). Each transport to a
    project records the rule of its company when it is saved and submitted (`Equipment Transport.move_day_rule`,
    read-only, not copied on amend, part of the cancel check), so a later change of the setting never changes how an
    approved move is applied or cancelled. Transports recorded before this change have no rule and keep the next-day
    behaviour. `card.transfer._apply_row_transfer`, `_written_by`, `check_cancel_allowed`. Card-day protection stays:
    under the move-day rule a submitted card day of the old project on the move day refuses the transport
    (`_refuse_dropped_card_days`), a machine that arrived on a project that day cannot leave it for another project the
    same day, and a submitted card day of the new project on or after the day its assignment starts refuses the cancel.
    First entries and moves to a workshop, storage or the supplier are unchanged.
  - **Impact:** permissions — none widened (the setting is permission level 1). Accounting — none directly; under the
    move-day rule the move day's card and cost belong to the new project. Data — none written on deploy. API — none.
  - **Rollback:** code and schema. A transport submitted under the move-day rule keeps assignments that end the day
    before the move; an older version cancels it only if the old assignment ends on the move date, so cancel such
    transports before a rollback or fix forward.
- **`is_unit_component` is derived from the units' component tables** (#42, WP-05; FR-057, FR-115; PR #187).
  - **Reason:** the flag was a manual tick, so a piece could carry its own monthly card while its unit's card billed
    the same days (FR-057 open point).
  - **Change:** the field is read-only and maintained by the server: ticked while a unit's component row lists the
    equipment with no To date (`sync_unit_component_flags`, on the unit's save and delete and on a component row
    inserted or saved on its own; a comment records each change; `move_component` syncs once after both units are
    saved). A save never writes it. The monthly card refuses working hours of a piece on a day inside a component
    period of any unit (`CardMonthlyCard._refuse_unit_component_days`; 0-hour rows pass, as in
    `validate_card_days`), and `get_card_context` no longer offers those days to the form. A piece no unit lists but
    whose flag was ticked before still takes no card at all. `resync_unit_component_flag` (`methods=["POST"]`, Card
    Manager level: the flag's permission level 1) sets one equipment to its derived value.
  - **Patch `card.patches.v4_6_0.derive_unit_component_flag`:** writes the flag only where it is unambiguous (the
    equipment is listed in a unit's component table: ticked when a row is open, cleared when every row is closed);
    keeps a ticked flag on equipment no unit lists (ambiguous: the unit's table may never have been filled in); lists
    those and every rented unit or rented component in one Error Log entry ("CARD unit records to review (#42)").
    Only the flag column is written (no modified date, no Version). Idempotent: a second run writes nothing.
  - **Impact:** permissions — none widened. Accounting — a piece can carry its own card for days outside its unit
    periods (before: refused for the whole time the tick was set); a listed piece that had no tick now takes no card
    for its unit days. Data — the patch above. API — one new POST method.
  - **Rollback:** an older version reads the flag as a manual tick again; the values the patch wrote stay and are
    correct for the component tables.

### Fixed
- **Diesel fill: a rejected fill returned to review re-checks its meter photos** (FR-085, PR #165). A rejected fill does not
  hold its photo, so a corrected fill may reuse it. Moving the rejected fill back to Draft or Needs Review did not check
  the photos again (the check ran only when a photo or the company changed), so two live fills could prove one photo
  and count the same litres twice. `ProjectDieselFill._check_photos` now also runs when the stored review status was
  Rejected and the new one is not; the save is refused while another live fill uses the photo. Tests:
  `card/tests/test_diesel_session_evidence.py` (2 new). Impact: no permission, schema, data or API change; no
  accounting effect (fills post only after approval). Rollback: revert the commit.

### Documentation
- **README rewritten** (PR #136). New "How CARD works" section with a flow diagram and five steps in order
  (equipment, transport, project assignment, monthly card, daily hours), in English with an Arabic summary.
  Grouped badges (CI, Linters, CodeQL, Codecov, release, license, platform), a screenshots gallery of the
  main pages (CARD v4.1.2, fictional test data, new files in `.github/images/`), a table of the CI
  workflows, the report count corrected to 19, and the Features section brought up to v4.5.0 (settlement,
  posting integrity, transport cost responsibility, equipment financial privacy). Requested by the owner. Documentation only: no change to
  code, permissions, accounting, data or the API. Rollback: revert the commit.
- **No user impact (listed for completeness):** #136 is the README rewrite above; #148 records the v4.4.2, v4.4.3 and platform-update deployments in
  `docs/releases/DEPLOYMENTS.md`; #149 bumps `actions/upload-artifact` from 4 to 7 in the upgrade rehearsal
  workflow; #166 raises the build requirement to `flit_core >=4.2.0,<5`; #204 syncs the feature registry with the
  merged pull requests. Impact on permissions, accounting, data and the API: none. Rollback: revert the commit.

### Security
- **Reviewer is not the approver on equipment needs** (FR-121, PR #189; refs #125, #51; FR-005 open point).
  - **Reason:** reviewer and approver of an Equipment Needs Review were separated by role only; one user holding
    both roles could review, edit or submit a review and then approve it.
  - **Change:** Equipment Needs Review records on the server who submitted it (`submitted_by`, new read-only field,
    set in `before_submit`) and every user who saved the draft (`edited_by`, new hidden field, from the stored value
    as in `EquipmentTransport._record_editor`); neither can be set by the client. `card.materials.approve_review`
    (the only approve entry point) refuses with a PermissionError every preparer (`review_preparers`): the reviewer
    (`supervisor`, or the owner of a legacy review without one), the submitter and every recorded editor. No role
    is exempt: Administrator and System Manager are refused like anyone else. The form hides Approve from them.
    Enforced by default (FR-005 already called for it).
  - **Impact:** permissions — narrower: whoever prepared a review cannot approve it; another Card Manager (or
    System Manager) approves it. Accounting none (approval still makes draft Material Requests only). Data — two
    new columns, empty on existing reviews (a legacy pending review falls back to its supervisor or owner); no
    record is changed, an already approved review stays approved. API — `approve_review` can now raise
    PermissionError. Three new Arabic strings.
  - **Rollback:** revert the commit; an older version ignores the two columns.
- **Attachment validation and privacy** (H-CARD-1, H-CARD-2; FR-099; PR #162).
  - **Reason:** meter photos, the custody receipt, fitment evidence, the transport authorization document and the Card
    Equipment registration / inspection / insurance / TUV files accepted any bytes under any name, and the transport
    document and the equipment files could be a public file or a file of another record.
  - **Change:** a shared validator (`card/attachment_validator.py`: `check_attachment_content`, `require_record_file`,
    `claim_file`) accepts only JPEG, PNG, WebP or PDF, detected by content (the file name must agree), up to 10 MB;
    an image must decode and stay at or below 50 megapixels (checked from the header before decoding; Pillow's
    decompression-bomb warning is an error); meter photos accept images only. Bytes are read through the File API
    (`File.get_content(encodings=())`). Used by `ProjectDieselFill._check_photos`, `EmployeeToolCustody` (signed
    receipt), `CardEquipmentPart` (fitment evidence), `equipment_transport._billing_values` (authorization document)
    and `CardEquipment.validate_document_files`. It runs only when a file is new or changed (not on a company change,
    not when an amendment keeps the amended record's photo or receipt), so evidence saved earlier stays valid. The
    transport document and the four equipment document files must be private files of their own record; the user's
    own unattached upload is claimed by the record on save. The old "any readable File with this URL" check is
    removed. The four equipment document fields are `no_copy` (Duplicate no longer copies them).
  - **Impact:** permissions and API: stricter; a save with a non-allowed, oversize, undecodable, public or another
    record's file is refused. Data: no patch, nothing changed or deleted; files already stored as public stay public
    until a separate owner decision; unchanged legacy values are not re-checked. Schema: `no_copy` on four Card
    Equipment fields (DocType JSON, applied by `bench migrate`). Accounting: none.
  - **Known limits** (accepted by the owner, review of PR #162): HEIC photos are refused (Pillow has no decoder);
    save them as JPEG first. A financial re-decision that keeps a transport's existing authorization document is
    refused when that document is an older unattached upload: the accountant uploads it again. When the same user
    saves two records at the same time with one unattached upload, only the first record claims the file; the
    second keeps a link to a file attached to the first.
  - **Translations:** the eleven new messages of `card/attachment_validator.py` are translated in
    `card/locale/ar.po` (and listed in `main.pot`).
  - **Convention:** an Attach / Attach Image field that holds evidence or a document is validated in its controller
    with `card.attachment_validator` when the value is new or changed.
  - **Rollback:** revert the merge of PR #162 and migrate (the `no_copy` flags return); nothing to undo in data. File
    rows claimed by a record stay attached to it (they are that record's own files).
- **Read endpoints GET-only and diesel fill company permission** (H-CARD-3, H-CARD-4; FR-098; PR #161).
  - **Reason:** a whitelisted function without `methods=` answers GET, POST, PUT and DELETE, and Frappe checks CSRF
    for the last three only; read handlers should answer GET. Project Diesel Fill had no record-level company check.
  - **Change:** `card.api.party_figures`, `card_suppliers_query`, `card_customers_query`, `report_defaults`,
    `card.diesel.get_card_diesel` and `card_equipment.get_shift_heatmap` declare `methods=["GET"]`;
    `card_project_options` and `card_company_options` declare `methods=["GET", "POST"]` (read-only; the Autocomplete
    control posts). Their direct Desk callers pass `type: "GET"`. Project Diesel Fill gets a `has_permission` hook
    (`project_diesel_fill.has_diesel_fill_permission`): the company sent and the stored company must both be in the
    user's permitted companies, the same pattern as Card Monthly Card and Equipment Transport. Frappe 16 consults a
    DocShare after a controller denial, so a DocShare `validate` hook (`deny_cross_company_share`) refuses sharing a
    fill with a user outside its company, or with everyone. Every `@frappe.whitelist` in CARD now declares `methods=`
    (re-checked after the merge of v4.5.0, including `statement_pdf.download_pdf` and
    `journal_link.link_accrual_journal`, both POST). The two new share refusal messages are translated in
    `card/locale/ar.po` (and listed in `main.pot`).
  - **Impact:** permissions — narrowed only (cross-company read, write and share of a fill refused; unrestricted users,
    System Manager and Administrator unchanged). API — the six GET-only functions refuse POST, PUT and DELETE; CARD
    Mobile calls none of them. Accounting, data, schema — none. No patch.
  - **Rollback:** revert the merge of PR #161; nothing to undo in data. Shares refused while it ran were never created.

### Migration
- `bench migrate` runs three new `post_model_sync` patches, each idempotent (a second run writes nothing):
  `card.patches.v4_6_0.derive_unit_component_flag` (writes `is_unit_component` only where a unit's component table
  gives an unambiguous value; lists the rest in one Error Log entry), `card.patches.v4_6_0.seed_stop_reasons` (three
  non-billable Card Stop Reasons per company that has cards) and `card.patches.v4_7_0.seed_diesel_price_schedule`
  (one Card Diesel Price row per company with a diesel price, same price).
- Schema: new DocTypes Card Stop Reason and Card Diesel Price; new columns on Card Company Settings, Card Equipment,
  Card Monthly Card, Card Monthly Card Day, Card Settings, Equipment Needs Review, Equipment Transport and Project
  Diesel Fill; `no_copy` on four Card Equipment document fields; four settings hidden. Migrate also adds four reports,
  the page `card-monthly-posting`, the Dashboard Chart Source Card Monthly Values and re-imports the workspace
  fixtures. It writes no GL entry, card amount, day row, fill price or transport.
- Manual, not done by migrate (separate approval): the Card Equipment accounting dimension
  (`bench --site <site> execute card.dimension.ensure_card_equipment_dimension`), the per-company settings and the
  internal rates. Rebuild open CARD draft postings that hold a project-tank fill before submitting them.
- Rollback: the last recorded version on Production is v4.4.3. Its code runs on the 4.6.0 database (it ignores the new columns and
  tables), but a code rollback does not remove the columns, the two tables and their seeded rows, the patch-written
  component flags or the cancel reasons and comments. Prepare it as described in
  [docs/releases/v4.6.0.md](docs/releases/v4.6.0.md#126-rollback-plan) (other-party transports, move-day transports,
  `diesel_unit_price`, v4.5.0 journal links); a database restore only when it loses no Production transaction.

### Known limitations
- Default-on behaviour changes (owner decisions): GET-only read functions, stricter attachments (HEIC refused),
  owned-only units, reviewer not approver, mandatory cancel reason (Workflow cancel action, List view bulk cancel and
  "cancel all linked documents" refused for the three doctypes), `diesel_unit_price` read-only once a company has a
  schedule, older drafts with a project-tank fill refused on submit until rebuilt.
- Equipment Partial Margin and Equipment Maintenance Cost need the Card Equipment dimension (missing on Production per
  records). The stop-reason seed covers companies with cards at migrate time only; `min_hours` is not read. Project
  Diesel Fill has no equipment-status guard yet (PR #200). Card Settings exposes every company's schedule rows to
  level-1 readers. Meter extraction is off by default and needs an IP-literal worker URL. The posting page is not on
  a workspace sidebar; Accounts User read of GL Posting Log is an open owner decision. Details per pull request:
  [docs/releases/v4.6.0.md](docs/releases/v4.6.0.md#10-known-limitations--verified).

## [4.5.0] — 2026-11-09

Minor release on top of v4.4.3 (PR #182): settlement phase 1. An accountant links an existing supplier accrual
Journal Entry to the monthly cards it recognised, so CARD never invoices them again, and the new read-only Card
Settlement Status report shows paid and remaining per card from the ledger. No patch, no schema change, no GL write;
one new POST API method and one new report. Accounting stays disabled unless the site enables it.

### Added
- **Settlement phase 1: link a supplier accrual Journal Entry to its cards; Card Settlement Status report** (owner
  decisions 2026-11-09, Q2/Q3/Q8).
  - **Reason:** supplier cards recognised by hand with a Journal Entry (expense debit, supplier credit) showed as "not
    invoiced through CARD", and the monthly posting would have invoiced them a second time.
  - **Change:** `card.gl.journal_link.link_accrual_journal` (`methods=["POST"]`, accountant roles, read and submit right
    on the Journal Entry) records a Linked GL Posting Log of type Journal Entry for submitted supplier cards of the
    same company and supplier, when the entry is an ordinary journal entry (no opening entry, no row against
    another document) that credits exactly that supplier, and its credit less its tax rows equals the cards' net
    (a difference only with an accepted reason). The cards are reserved: the monthly posting and every other link skip
    them, and the statements count them as recognised (`card.reconciliation.cards_invoiced`). Cancelling the Journal
    Entry frees them (`Journal Entry` `before_cancel`). New read-only report **Card Settlement Status** (System Manager,
    Accounts Manager; ledger access required): per card the recognising document, the card's share, paid, credit notes and
    remaining from the Payment Ledger Entry (the user's card permissions apply), allocated oldest first, a
    "ledger entry not found" status instead of a settled one, and the party's payments not allocated to a document
    up to the end date.
  - **Impact:** permissions — none widened (new report for accounting roles only). Accounting — nothing is posted,
    created or changed in ERPNext; no GL write. Data — a GL Posting Log row per link; the card's `posted` and
    `gl_posting` fields. Schema — none (the Journal Entry option already existed). API — one new POST method.
  - **Rollback:** an older version ignores Journal Entry logs: the cards count as not invoiced again and the monthly
    posting would build them; cancel or keep accounting disabled until the link is supported.

## [4.4.3] — 2026-11-09

Patch release on top of v4.4.2 (PR #180): the PDF button of the Equipment Supplier Statement renders with the
Frappe Chrome PDF generator on one A4 portrait page, and the statement font is no longer replaced by a site print
style. No patch, no DocType or schema change, no change to permissions or accounting; one new POST API method.

### Changed
- **CI: the PR title check runs on `pull_request`** (owner, 2026-11-09). GitHub blocks `pull_request_target` in public
  repositories by default (enforced from 2026-12-02; a brownout on 2026-11-09 stopped the check). The check only reads
  the title, so the read-only `pull_request` token is enough. No change to the app, permissions or data.

### Fixed
- **Arabic messages of the statement PDF**: the three new messages of `statement_pdf.py` are translated (commit
  `5c63b8d`).
- **Equipment Supplier Statement PDF and print** (owner, 2026-11-09).
  - **Reason:** the report PDF button used the standard wkhtmltopdf path, which misshapes the Arabic alef after a
    joining letter ("حساب", "الصافي"). A site print style can set every print font with `!important`, so the browser
    print showed another font. In landscape, the signatures moved to a second page.
  - **Change:** the PDF action of this report only posts the filters to the new
    `card.card.report.equipment_supplier_statement.statement_pdf.download_pdf` (`methods=["POST"]`). The server runs
    the report with the user's permissions (report access, print permission on Card Monthly Card, company check),
    builds the page itself with the CSS of the print template, and renders it with the Frappe Chrome PDF generator
    (`frappe.utils.pdf.get_chrome_pdf`). The endpoint never accepts HTML from the browser. Other reports keep the
    standard PDF. The template font rule is `!important` and more specific than `.print-format *`; the site print
    style is not changed. The page is A4 portrait; the signatures and the issued-by line stay together on one level.
  - **Impact:** permissions — none widened (same rights as running and printing the report). Accounting, data, schema
    — none. API — one new POST method. An Access Log row is written for each PDF, as for the standard report PDF.
  - **Rollback:** a v4.4.2 image restores the wkhtmltopdf PDF; the A4 print format needs the forced re-import of the
    v4.4.2 file (`import_file_by_path` with `force`).

## [4.4.2] — 2026-11-09

Patch release on top of v4.4.1 (PR #178): the A4 supplier statement prints every card of the period and totals
from the cards only. No patch, no DocType or schema change, no change to permissions, accounting, data or the API.

### Changed
- **Equipment Supplier Statement A4: every card, card totals and full period dates** (FR-089; PR #178, commit
  `6a16f52`; Owner requests 2026-11-09, after the v4.4.1 check showed a supplier with un-invoiced cards printing
  all-zero ledger totals; branch `fix/statement-totals-card-net`). The print lists every row of the period:
  project, equipment (sub-heading) and every card with its shift, numbered, whatever their count. The totals come
  from the cards only: cards net for the period and, when positive, the work done not yet invoiced through CARD
  (before VAT; no VAT is computed). The ledger lines (opening, invoices, payments, closing) are no longer printed
  and no footnote is printed (the server note still prints only when the period has no rows). A last line reads
  "Issued by the electronic system of <company>" (the company comes from the filter; nothing hard-coded). The
  period prints as full dates (first day of the start month to the last day of the end month), as the report
  computes it. Font: Noto Sans Arabic (owner 2026-11-09) — the installed font first (server PDF), the app's
  bundled copy (`/assets/card/fonts`) as a fallback for browsers without it; the CARD document prints already use
  it. Files: `equipment_supplier_statement.html`, `equipment_supplier_statement_a4.json` (`modified` bumped),
  `card/locale/ar.po`, `card/locale/main.pot` (new CARD msgids "Cards net for the period", "Work done not yet
  invoiced (before VAT)", "Issued by the electronic system of {0}"), `card/tests/test_supplier_statement_print.py`.
  The report code (`equipment_supplier_statement.py`, which already sends the `net_cards` and `not_invoiced`
  summary keys) is unchanged. Impact: display only; no change to permissions, accounting, data or the API.

### Migration

- **Patches:** none. `card/patches.txt` is unchanged; `bench migrate` runs no CARD data patch.
- **DocType / schema:** no change. No new column, field level, role or DocPerm.
- **Records synced by `bench migrate`:** only the standard Print Format `Equipment Supplier Statement A4` (file
  `modified` 2026-11-09 23:00, newer than the v4.4.1 row). The other print formats and the fixture are unchanged.
- **What migrate does not write:** no card, transport, fill, receipt, posting, GL Posting Log or settings value;
  no GL entry; no role or permission change.
- **Code:** restart the web and background workers after the update (normal for an image deploy); compile the
  CARD translations (`ar`) into the image as before, or the new labels print in English.
- **Rollback:** last stable version v4.4.1 (runs on Production since 2026-11-09). v4.4.1 code runs on the v4.4.2
  database (no schema change). A plain migrate does **not** restore the v4.4.1 A4 format (its file is older than
  the row): re-import it from the v4.4.1 file with `force` (steps on the v4.4.2 release page).

### Known limitations

- Published ≠ deployed: deployment of 4.4.2 to any site is a separate, site-verified fact.
- The PDF button of the A4 supplier statement (a Script Report print) still uses frappe `report_to_pdf`, which
  always renders with wkhtmltopdf, so its PDF can still break Arabic letter joining; use the browser Print of
  the report, which uses the installed or bundled Noto Sans Arabic.
- The printed totals no longer show the supplier's ledger balance (opening, invoices, payments, closing); the
  screen report and the ERPNext ledger keep it. "Work done not yet invoiced" is before VAT; no VAT is computed.
- A period with many cards prints on several A4 pages; a print of a real long period is not part of the release
  evidence.

## [4.4.1] — 2026-11-09

Patch release on top of v4.4.0 (PR #175): display fixes found in the v4.4.0 production check. The CARD document
prints use frappe's Chrome PDF generator, because wkhtmltopdf broke Arabic letter joining in their PDF, and the
A4 supplier statement prints a short statement of totals. No patch, no DocType or schema change, no change to
permissions, accounting, data or the API (the report summary items gain an added `key` field).

### Fixed
- **CARD document prints: Arabic letter joining in the PDF** (FR-055, FR-045; PR #175, merge `beca0df`; Owner
  request 2026-11-09; branch `feat/supplier-statement-simple-totals`). `pdf_generator` of
  `Card Monthly Card Print`, `Equipment Transport Print`, `Project Diesel Fill Print`, `Tool Handover Receipt`
  and the fixture `كارت تشغيل شهري` changes from `wkhtmltopdf` to `chrome`: the v4.4.0 deployment check found
  wkhtmltopdf breaking Arabic letter joining (alef after a joining letter), while the Chrome generator printed
  Arabic correctly on the same site. Report prints (the PDF button of the A4 supplier statement) still go
  through frappe's `report_to_pdf`, which always uses wkhtmltopdf (see **Known limitations**); their browser
  Print is unaffected. Files: the four print format JSON files and `card/fixtures/print_format.json`
  (`modified` bumped), `card/tests/test_print_formats.py` (every CARD Jinja document print uses `chrome`).
  Impact: display only; no permission, accounting, data or API change.

### Changed
- **Equipment Supplier Statement A4: short totals** (FR-089; PR #175, merge `beca0df`; Owner request
  2026-11-09). The printed totals keep only opening balance + period charges (incl. VAT) − payments = closing
  balance (with ledger access), the card net (without), or equipment / days / hours (owned equipment). The
  reconciliation figures (accrual vs. invoiced through Card, invoices outside Card) and the reconciliation notes
  stay on the screen report and are no longer printed (the server note prints only when there are no rows). The
  report summary items carry a stable `key` so the print picks them whatever the language. The closing balance
  is now rounded from the rounded opening, charges and payments so the printed lines add up to the cent. New
  CARD msgid "Period charges (incl. VAT)"; "Payments" uses the existing erpnext translation. Files:
  `equipment_supplier_statement.py` / `.html`, `equipment_supplier_statement_a4.json` (`modified` bumped),
  `card/locale/ar.po`, `card/locale/main.pot`, `card/tests/test_report_access.py`,
  `card/tests/test_supplier_statement_print.py`. Impact: display only; no permission, accounting, data or API
  change (the summary `key` is an added field; no stored data).

### Migration

- **Patches:** none. `card/patches.txt` is unchanged; `bench migrate` runs no CARD data patch.
- **DocType / schema:** no change. No new column, field level, role or DocPerm.
- **Records synced by `bench migrate`:** the five standard Print Formats `Card Monthly Card Print`,
  `Equipment Transport Print`, `Project Diesel Fill Print`, `Tool Handover Receipt` and
  `Equipment Supplier Statement A4` (file `modified` 2026-11-09 16:10, newer than the v4.4.0 rows), and the
  Print Format fixture `كارت تشغيل شهري` (fixtures are re-imported with `force` on every migrate).
- **What migrate does not write:** no card, transport, fill, receipt, posting, GL Posting Log or settings value;
  no GL entry; no role or permission change.
- **Chrome PDF generator:** the four document formats and the fixture need frappe's Chrome PDF generator to work
  on the site. On Production a standard Sales Invoice printed correctly with the Chrome generator during the
  v4.4.0 check (2026-11-09) (Partially Verified); print each CARD document format once after the deploy.
- **Code:** restart the web and background workers after the update (normal for an image deploy); compile the
  CARD translations (`ar`) into the image as before, or the new label prints in English.
- **Rollback:** last stable version v4.4.0. v4.4.0 code runs on the v4.4.1 database (no schema change; the extra
  summary `key` is unused). A plain migrate does **not** restore the v4.4.0 standard print formats (their files
  are older than the rows): re-import the five from the v4.4.0 files with `force` (steps on the v4.4.1 release
  page). The fixture returns to its v4.4.0 content on that migrate.

### Known limitations

- Published ≠ deployed: deployment of 4.4.1 to any site is a separate, site-verified fact.
- The PDF button of the A4 supplier statement (a Script Report print) still uses frappe `report_to_pdf`, which
  always renders with wkhtmltopdf, so its PDF can still break Arabic letter joining; use the browser Print of
  the report instead.
- The Chrome generator on CARD prints of a real site is checked only through a standard Sales Invoice; a printed
  PDF of each CARD format after the deploy is not part of the release evidence.

## [4.4.0] — 2026-11-09

Minor release on top of v4.3.0: the six CARD print formats (the five document prints and the A4 supplier
statement) take the owner-approved standard Frappe print style, print in the print language with its page
direction, and the supplier statement hides empty Additions/Deductions columns. New Jinja method
`card.print_utils.card_print_is_rtl`. Backward compatible; no patch, no DocType or schema change, no change to
permissions, accounting, data or the API.

### Improved
- **CARD print formats: standard print style and the print language** (FR-055, FR-045, FR-083; PR #172, merge
  `e1cc2c4`, with fix `de3643d`; Owner request 2026-11-09; branch `feat/card-prints-standard-style`). The five CARD document print formats, `Card Monthly Card Print`, the
  fixture `كارت تشغيل شهري` (name unchanged), `Equipment Transport Print`, `Project Diesel Fill Print` and
  `Tool Handover Receipt`, now use the owner-approved SDCE print design of the Equipment Supplier Statement:
  the standard Frappe print look with the Frappe v16 print greys as literal colours (text #171717, labels
  #7c7c7c, table header #f3f3f3, borders #d1d8dd, heading underline #aaa; no navy band, coloured boxes,
  CSS variables or remote fonts, so the wkhtmltopdf PDF keeps them). Company name above the title, document
  details as label/value lines, row tables with a grey header and centred cells (text follows the page
  direction, numbers read left to right and are right-aligned, dates and counts centred), the totals as
  label/value lines at the end side of the page with the net or grand figure last and bold, signature lines
  at the bottom. The monthly card shows its additions/deductions, card totals and the settlement of each
  billed side in three columns so a sub-rental card with adjustments still fits one A4 page; the transport
  print lists its equipment with their cost shares; the tool receipt lists the tool, quantity and serial
  number. The page direction follows the print language, read at render time by the new Jinja method
  `card.print_utils.card_print_is_rtl` (frappe `is_rtl()` plus Urdu, as CARD Mobile does; `hooks.py` jinja), and every fixed text is translated
  (25 new CARD msgids in `ar.po` / `main.pot`, CARD-specific where frappe or erpnext translate the generic
  word differently, e.g. "Card totals", "Amount summary"); stored Arabic option values (shift, ownership,
  direction, rate type, day status, adjustment type) print through the existing `en.po` entries, the weekday
  from the date in the print language. Business logic unchanged: which blocks and sides print, the
  supplier/customer sums and the nets are the same; every data value stays escaped (the fixture now escapes
  its values too). Wkhtmltopdf geometry fixes are kept (`.print-format` override, `text-rendering: auto`, no
  rowspan, one font weight per cell). The status of a cancelled transport or diesel fill prints as
  "(Cancelled)" / "(ملغي)" and a draft as "(مسودة)" (core translated "Draft" as a project). Tests:
  `test_print_formats.py` renders under Arabic (labels unchanged) with the new totals markup, plus one test
  for the English print (`dir="ltr"`, English labels, the same amounts) and Urdu (`rtl`); the class
  compiles Card's ar catalogue into a temporary folder so the Arabic assertions do not depend on a stale
  bench catalogue. The fixture's `default_print_language` (was `en`) is cleared so it prints in the user's
  language like the other formats; the Friday row is now taken from the date. Files: the four print format JSON
  files (`modified` bumped so `bench migrate` re-syncs them), `card/fixtures/print_format.json`,
  `card/locale/ar.po`, `card/locale/main.pot`, `card/tests/test_print_formats.py`, `card/print_utils.py`,
  `card/hooks.py`. Impact: display only; no
  change to permissions, accounting, data or the API. Rollback: not by `bench migrate` alone (the older format files
  are not re-imported); see **Migration → Rollback**. No data to restore. Fix `de3643d`: the Friday row condition
  is parenthesised (Jinja refused a bare conditional expression in an `{% if %}` test; seen in the upgrade
  rehearsal) and a new test compiles every CARD Jinja print format.
- **Equipment Supplier Statement A4: new print style** (FR-089; PR #171, merge `22ae3e6`, with fix `e52d43f`;
  Owner request 2026-11-09). Looks like a
  standard Frappe print: colours and borders follow Frappe v16 `templates/styles/standard.css` and
  the espresso gray scale (text #171717, labels #7c7c7c, table header #f3f3f3, borders #d1d8dd,
  heading underline #aaa). Company name above the title, the statement details (company, type,
  supplier, from, to, issue date) as label/value lines, project rows and the grand total in bold.
  The print sets its own text direction from the user's language (`frappe.utils.is_rtl()`, as the
  report print page does): text cells follow it, numbers read left to right and are right-aligned
  so the decimals line up, dates, counts and the row number are centred, cells are vertically
  centred.
  The summary figures moved below the rows as a "Totals" table (الإجماليات; CARD-only msgid
  "Statement totals", so the generic frappe "Totals" translation is not overridden), placed right under the last (amount) columns, at the end side
  of the page as in a standard invoice. The print no longer shows the equipment number, rate type or rate
  columns (the screen report keeps them); the remaining widths fill the A4 landscape width.
  The Additions and Deductions columns print only when some row has a value; the other columns
  share the freed width and the Totals table follows the width of the amount columns. Everything
  the template writes is translated into the user's language, including the statement type (the
  filter stores the Arabic option value; it now prints as "Supplier" / new msgid "Owned
  equipment"). Names in the data (company, supplier, project, equipment, card) print as stored.
  Files: `equipment_supplier_statement.html` and the `Equipment Supplier Statement A4` Print Format
  (`modified` bumped so `bench migrate` re-syncs it). Same data, filters and escaping; literal
  colours (no CSS variables, no remote font) so the wkhtmltopdf PDF keeps them; font Cairo when
  installed, else the bundled Noto Sans Arabic. The logo comes from the Letter Head chosen in the
  print dialog (nothing company-specific is hard-coded). Impact: none on permissions, accounting,
  data or the API. Rollback: not by `bench migrate` alone (the
  older format file is not re-imported); see **Migration → Rollback**. No data to restore.

### Migration

- **Patches:** none. `card/patches.txt` is unchanged since v4.2.2; `bench migrate` runs no CARD data patch.
- **DocType / schema:** no change. No new column, field level, role or DocPerm.
- **Records synced by `bench migrate`:** the five standard Print Formats `Card Monthly Card Print`,
  `Equipment Transport Print`, `Project Diesel Fill Print`, `Tool Handover Receipt` (file `modified`
  2026-11-09 14:00) and `Equipment Supplier Statement A4` (2026-11-09 13:30), re-imported because their file is
  newer than the database row; the Print Format fixture `كارت تشغيل شهري` (html/css replaced,
  `default_print_language` cleared from `en`; fixtures are re-imported on every migrate).
- **What migrate does not write:** no card, transport, fill, receipt, posting, GL Posting Log or settings value;
  no GL entry; no role or permission change.
- **Code:** `hooks.py` adds the Jinja method `card.print_utils.card_print_is_rtl`; restart the web and background
  workers after the update (normal for an image deploy). Compile the CARD translations (`ar`) into the image as in
  previous deployments, or the Arabic print shows the English labels.
- **Rollback:** see the v4.4.0 release page. Last stable version: v4.3.0. v4.3.0 code runs on the v4.4.0
  database (no schema or data change). Checking out v4.3.0 and running `bench migrate` does **not** restore the
  v4.3.0 standard print formats: frappe re-imports a standard document only when its file `modified` is newer
  than the database row, and the v4.3.0 files are older. The four restyled DocType formats call
  `card_print_is_rtl()`, which v4.3.0 does not register, so they fail to render after a code-only rollback until
  the v4.3.0 formats are re-imported with `force` (steps on the release page). The fixture returns to its v4.3.0
  content on that migrate (fixtures are imported with `force`).

### Known limitations

- Published ≠ deployed: deployment of 4.4.0 to any site is a separate, site-verified fact.
- The print look was checked by template tests and a Jinja compile test in CI; a printed PDF from a real site
  (wkhtmltopdf, A4 fit of a sub-rental card with adjustments) is not part of the release evidence.
- Names stored in the data (company, supplier, project, equipment, card, Data fields) print as stored, so an
  English print can still show Arabic names.
- A4 supplier statement: Landscape must still be chosen in the PDF dialog.
- In a language without a CARD catalogue the CARD-specific labels print in English.

## [4.3.0] — 2026-11-09

Minor release on top of v4.2.2: posting integrity and project/equipment cost allocation for CARD postings,
transport cost responsibility, three read-only reconciliation and review reports, Card Equipment financial
privacy, a night-shift customer rate, an A4 supplier statement, and the first version compatible with the ERPNext
v16.54.0+ portal catalog / Company Restriction (shown by CI). Breaking changes are listed under **Migration**.

### Security
- **Card Equipment financial privacy** (FR-096, PR #156, Owner decision 2026-10-31). The Asset purchase value (a read-only
  copy of the Asset's `net_purchase_amount`), the internal hourly rate, the Asset cost center and the equipment's own
  cost center (filled from the Asset) were readable by every reader of the equipment, including Card User and Card
  Supervisor, who have no Asset read; the supplier's hourly rate (`approved_hourly_rate`) was readable by Card
  Supervisor. These four fields move to permlevel 2, read by System Manager, Card Manager and Accounts Manager (System
  Manager and Card Manager keep editing them); `approved_hourly_rate` moves to permlevel 1 with the supplier rate it is
  computed from. Frappe applies these levels to the form, the REST API, list and report queries and their exports.
  The change history (Version) reaches every reader of a document at any level, so new Versions of Card Equipment
  keep who changed a field above level 0 and when, but not its values (`card.field_privacy`, a Version
  `before_insert` hook). Existing history holds none of the financial values on Production (checked). Nothing is
  deleted: the fields, their values and the columns stay; the server-side code that reads them is unchanged.
  Impact: permissions narrowed (no role gains access; Card User can no longer read or set the equipment cost center),
  no schema or data change, no accounting change. Rollback: revert the commit and migrate; the fields return to their
  former levels.
- **Asset prefill follows the equipment's field levels** (FR-097, PR #157, Owner decision 2026-10-31, after FR-096). The
  values CARD sends to the equipment form from a chosen Asset (`card.api.get_asset_prefill`, and the prefilled form
  that `card.api.create_equipment_from_asset` returns when something is still missing) included the Asset's cost
  center for any user who may read the Asset, also when the user may not read the equipment's cost center
  (permlevel 2). Both responses now hold only the Card Equipment fields the user may read (Frappe's permitted fields
  for the user). Authorized users (System Manager, Card Manager, Accounts Manager) still receive the cost center; what
  is saved is unchanged (the Asset cost center and purchase value are still copied onto the record on save). Impact:
  API responses narrowed, no permission, schema, data or accounting change. Rollback: revert the commit.

### Added
- **Night-shift customer rate on Card Equipment** (FR-109, PR #167, Owner decision 2026-11-08). A machine rented to a customer
  can carry a different price per shift (for example a crusher rented at one monthly price for the day shift and a
  lower one for the night shift, both on 26 days x 10 hours). Card Equipment gets an optional field
  `customer_rate_night` (Currency, non-negative, permlevel 1 like `customer_rate`, shown only for the customer-billing
  directions, tracked as a commercial field). A night-shift Card Monthly Card (`shift = ليلي`) of a customer-billing
  equipment mirrors this rate into its `customer_rate` (same basis `customer_rate_type`); a day-shift card, and a
  night card of an equipment without a night rate (empty or zero), keep the customer rate exactly as before.
  Submitted cards keep their stored values. Affected: `card_equipment.json/.py`, `card_monthly_card.py`
  (`before_validate` mirror), `card_monthly_card.js` (the form shows the night rate before save, display only), `card/constants.py` (`SHIFT_DAY`, `SHIFT_NIGHT`), `card/locale/ar.po`;
  tests `card/tests/test_shift_customer_rate.py` (8). Impact: one new nullable column; no permission widening; no
  accounting change (CARD writes no GL entries; the customer amount feeds the existing Sales Invoice flow); no API
  change. Rollback: revert the commit and migrate; the column stays in the database unused (Frappe does not drop
  columns), and draft night cards re-mirror the customer rate on their next save.
- **Equipment Meter Reconciliation report** (FR-094, PR #155, maintenance plan R1, 2026-10-31). A read-only Script Report
  (Card Manager, Accounts Manager, System Manager; the user's roles must also read Card Equipment, Card Monthly Card
  and Asset — on a standard site Asset is read by Accounts User, so a user needs both) that
  compares, per machine, the hour-meter readings recorded elsewhere on the site — the legacy fuelling log of another
  app when that DocType exists and the user may read it, and the hour-meter fields an Asset may carry — with the
  operating hours of CARD's submitted monthly cards over the same period. Meter readings are cumulative: only the
  differences between consecutive plausible readings count as hours. Each reading is checked: invalid, duplicate,
  backward, meter reset, impossible jump, and a "hours run" equal to the whole meter (ignored). It also flags a
  possible identity conflict between an Asset ID and its own name or item, Asset meter fields that disagree with the
  last plausible reading, and CARD hours that differ from the meter hours beyond a tolerance. It shows the kept
  maintenance policy (alert at 250 hours, oil change at 300) and sets no maintenance baseline: a baseline needs a
  verified reading and verified maintenance history.
  Impact: read-only (no write, link, post or change of any kind, also not to the other app's data), no schema
  change, no new role or permission, no dependency on another app (its DocType is looked up at run time), a sidebar
  link under Card Reports, Arabic strings. Rollback: revert the commit.
- **Asset Mapping Review report and minimum-input Create from Asset** (FR-095, PR #155, maintenance plan M1, 2026-10-31).
  A read-only Script Report (Card Manager, Accounts Manager, System Manager; roles must also read Asset and Card
  Equipment) classifies every
  submitted Asset of a company for an Owner decision: linked; linked to equipment that is not owned; linked with a
  type that differs from its category's type; not in CARD with an equipment type available; not in CARD without a
  type for its category; sold or scrapped. It also lists owned equipment without an Asset link and flags a
  possible Asset identity conflict. It creates nothing. "Create from Asset" on a new equipment form now asks for the
  Asset and its ownership (owned by default, or third party; a rented machine is refused — it never gets an Asset).
  When nothing else is needed (owned, the Asset category maps to an equipment type, a default daily-hours setting)
  the equipment is created at once with the user's own permissions and full validation; otherwise the prefilled
  form opens with the missing fields. One Asset still links to one equipment only; no Asset is ever created.
  Impact: `card.api.create_equipment_from_asset` (POST) takes optional `ownership` and `save`; without them it
  still inserts nothing and returns the prefilled owned equipment, which now also carries the default daily hours
  and a `missing` list of the fields left to complete (for a third-party machine always including its
  commercial terms, `rental_direction`); no schema change, no new role or permission, a sidebar link, Arabic strings.
  Rollback: revert the commit.
- **Transport cost responsibility** (FR-093, PR #154, integration plan P1-2, operational part, 2026-10-31). Equipment
  Transport asks one question, "Transport responsibility", with seven plain choices: the company bears the cost;
  the company pays and bills the customer; the company pays and recovers from the equipment supplier; the
  equipment supplier bears the cost; the customer pays the transporter directly; no transport charge; or
  "responsibility needs review" (unknown or unsupported — recorded, never costed or posted). From that choice the
  server stores the actual payer, the party that finally bears the cost, and the customer-billing and
  supplier-recovery eligibility apart. Only a move whose cost the company bears asks for a cost project — chosen
  explicitly, never taken from where the machine comes from or goes to (the form offers the source or destination
  project as a button only); a move to a workshop or storage takes the place's configured cost center, which must
  be a valid cost center of the company. A recharged move (customer or equipment supplier) carries no cost
  project. It waits for a financial decision — bill the customer (billing project, customer from that project,
  agreed amount, authorization reference, the accountant's confirmation; monthly invoice by default, a separate
  invoice needs the authorization document), absorb (reason), recover from the equipment supplier (amount;
  deduction from monthly dues by default) or return for correction — recorded by an Accounts Manager of the
  transport's company who did not create, edit or submit it, nor the transport it amends
  (`record_financial_decision`, POST, row lock; permlevel-1 fields with the approver and time; a generic comment
  ("Financial decision recorded.") and a Version with the status change only, so neither the decision nor an
  amount reaches readers without permlevel-1 access). Cancel and amend start a new decision. A read-only **Transport Accounting Review** report (Accounts
  Manager, System Manager) lists transports recorded before this change (readable as recorded, nothing filled in),
  responsibilities that need review and open or recorded decisions. Cost reports use the cost project for new
  transports.
  Disabled on purpose: customer transport invoicing, supplier recovery documents, Purchase Invoice posting of
  P1-2 transports (excluded from the monthly build and refused by "link supplier invoice"), any tax treatment,
  account mapping (5125/4160 not used) and any historical adjustment. Transports recorded before this change keep
  the P1-0 rules.
  Impact: schema (new Equipment Transport fields; `cost_borne_by` kept read-only for old records), a new POST
  method, a new report and sidebar link, Arabic strings; no new role; no GL. Rollback: revert the commit; the new
  columns stay in the database with their values and can be dropped only by a separate approved task. After a
  revert, transports recorded with a responsibility have an empty `cost_borne_by`, so the old monthly supplier
  build treats them as company-paid and refuses that supplier's month ("who pays this move is not recorded")
  until each such transport is cancelled and amended, or its old field is restored by a separate approved data
  task. This fails closed only for a revert to the P1-0 code (main before PR #154). Rolling back to v4.2.2 does
  not refuse: v4.2.2 posts such transports as company-paid, so the rollback plan for this release is a backup
  restore or a fix forward (see `docs/releases/v4.3.0.md`, section 12). The Transport Accounting Review report
  record also stays in the database and must be removed by that task.
- **Diesel Invoice Reconciliation report** (FR-092, PR #153, integration plan P1-1, 2026-10-31). A read-only Script Report
  (Accounts Manager, System Manager — the roles that read both diesel sessions and Purchase Invoices) that compares CARD diesel sessions (Project Diesel Fill) with the
  suppliers' own submitted Purchase Invoices for one company and a period. The litres are read from the invoice line
  text (the suppliers' invoices carry them only there); delivery charges, as a separate line or folded into the
  diesel line, are kept apart from physical diesel; the VAT basis of each invoice (VAT-inclusive, VAT-exclusive or
  unverified) comes from its own figures against the session price — never a company-wide assumption. Sessions
  match one delivery invoice (same supplier, date window, equal litres or litres + delivery charge, or amount only)
  or, for aggregated invoices, a period (sessions after the previous invoice up to the bill date); several suppliers
  can be reconciled as one delivery stream. Rows show the status, litres, gross, net, VAT, VAT %, projects and the
  evidence; exceptions: session without invoice, invoice without session, period litre gaps, lines without project.
  Each row states its match confidence: confirmed only by a document link (the session names the invoice);
  inferred from the invoice text (equal litres, or litres plus a delivery charge); estimated by amount or by period; the submitted/draft split of its sessions (and a "submitted only" filter), the physical
  diesel litres apart from the delivery-fee equivalent, the VAT as booked, and a project/equipment allocation check
  (reported, never changed). A period difference is a point to review, never a confirmed over-billing or missing
  payment.
  Impact: no write of any kind (no posting, link, save or submit), no schema change, no new role or permission (the
  user's roles must read Project Diesel Fill and Purchase Invoice; one permitted company); a new GET options method
  `card.diesel_reconciliation.diesel_supplier_options`; a sidebar link under Card Reports; Arabic strings. Rollback:
  revert the commit (nothing to undo in data).
- **A4 print of the Equipment Supplier Statement** (FR-089, PR #150, Owner request 2026-10-29): a standard Report
  Print Format `Equipment Supplier Statement A4` (JS, Arabic RTL, A4 landscape) and the same layout as the
  report's own print template. It prints the company, supplier, statement type and period, the report's
  summary figures at the top, the project and equipment rows with the grand total, and three signature lines
  (accountant, reviewer, supplier — the supplier line only on supplier statements), the report's notice line, and
  an "includes draft cards" note when drafts are included. Landscape is set in the page CSS; choose Landscape in
  the PDF dialog (the PDF engine follows the dialog). The report pre-selects the format in the PDF dialog; the Print dialog with
  an empty format uses the same template. Text is escaped. Display only: no permission, accounting, data or
  API change (`get_print_format_data` keeps the report's own permission checks). Rollback: remove the two
  print files and disable the Print Format record. New strings in `ar.po`.

### Improved
- **Agent skills rule** (owner decision 2026-11-02, documentation only). AGENTS.md "Skills": an official Frappe
  skill is installed only under a license that permits it and its content is never copied into the repository;
  the nonexistent `frappe-ui` skill is replaced by the official frappe-ui documentation and source; when an official
  skill is not available the agent records `SKILL NOT FOUND` and continues only with an owner-approved substitute
  listed in the new [docs/governance/SKILL-SUBSTITUTES.md](docs/governance/SKILL-SUBSTITUTES.md), else it stops;
  without `frappe-code-review` an independent review with the register's checklist is mandatory. No test, CI step,
  security scan, approval step or Production safeguard is removed. Impact: none on code, permissions, accounting,
  data or API. PR #160 (`65ad8e0`). Rollback: revert the commit.
- **Project/equipment cost allocation on CARD postings** (FR-091, PR #152, integration plan P1-0, 2026-10-30). Card, diesel
  and transport lines of CARD postings carry the project/equipment allocation instead of the company default. One
  rule (`resolve_cost_center`) applies to every line: the assignments of the line's equipment to its project that
  cover the line's days (a card's worked days, a direct fill's or transport's date, a tank-fill share's worked days; for a unit without its own
  assignment, its components' assignments) each give their cost center or, when empty, the project's; one result is
  used, different results refuse the build for review. Without an assignment the project's cost center applies.
  A cost center that is set but unusable (group, disabled, other company) refuses the build. The equipment's own
  (asset) cost center is never used for project work: a project without a cost center whose equipment has one is
  refused for review. A project line with no cost center at all is refused too: the Card Company Settings cost
  center is never used for project work (Owner decision 2026-10-30). A fill's own cost center still wins; the
  equipment (Card Equipment dimension) stays on every line. An equipment that worked on two projects in a month
  has one card per project.
  Transport (Owner decisions 2026-10-30) follows its explicitly verified cost bearer: only a move the company
  pays is billed (`cost_borne_by`; a move without the company recorded as payer is refused; moves paid by the
  equipment supplier or the customer are not on the transport supplier's invoice); a move to a workshop or storage
  takes the cost center configured for that place in Card Settings, only when the cost center copied on save is
  valid and is still the configured one. CARD records no cost-bearing project, and neither the project a move
  leaves nor the project it goes to (nor the equipment's or the company default cost center) is assumed, so every
  company-paid move to or from a project — first entry, transfer, return to the supplier, or a historical move
  without its origin — refuses the build for review; the transport record is kept unchanged and the accountant
  enters the supplier's invoice. This blocking is a temporary financial safety control, not the final design: P1-2
  adds explicit cost-bearing fields to the transport. Exception messages point to cancel and amend for submitted
  transports; the new messages have Arabic translations (`ar.po`, `main.pot`). Impact: GL cost centers of new CARD postings (project
  costing); builds are refused where Projects/assignments have missing or unusable cost centers and for every
  company-paid move to or from a project — check the data before release. No permission or API change; the P0 signature covers the new values. Rollback: revert the
  commits; submitted postings keep their cost centers.
- **Feature Registry: FR-093 to FR-097 marked implemented** (PR #159, documentation only). No user impact.

### Fixed
- **Catalog for Card portal roles under ERPNext Company Restriction; period-lock tests on the new Desk cancel**
  (FR-076, PR #169, CI, 2026-11-09). ERPNext `version-16` v16.54.0 registers `permission_query_conditions` hooks for Item,
  Customer, Supplier and `*` (Company Restriction). The restricted catalog read of the Card portal roles (Card
  Operator and the CARD Mobile catalog view) refused to read whenever any such hook existed, so after that ERPNext
  release their catalog, OEM numbers, alternatives, filters and the mobile item search would be empty (18 tests on
  CI). `card.catalog._read` now applies the hooks the way the latest frappe v16 `frappe.get_list` does (`_query_rule_criteria`: a string
  condition is wrapped as raw SQL, a pypika term is used as it is; `_get_all_with_rules` builds the same query with
  the query builder and adds them). A Permission Query server script still closes the restricted read. Readers of
  the DocType keep `frappe.get_list`. Frappe v16 from November 2026 also reloads the stored document on a Desk
  Cancel, so a changed date in the request is dropped instead of refused; the five Desk cancel-request tests in
  `test_period_lock_extra_keys` now check that the stored date never changes under either behaviour, and two
  new tests keep CARD's own refusal covered for a Python/API cancel that changes the date. Tests:
  `card/tests/test_catalog_query_rules.py` (7). Impact: the restricted read gains the same row rules as
  `frappe.get_list` (it can only narrow what it returns); no new role, permission, schema, accounting or API change.
  Production today has no Company Restriction (checked read-only 2026-11-09), so nothing changes there until
  ERPNext is updated. Rollback: revert the commit (the portal catalog is empty again on ERPNext v16.54.0 or later).
- **Test setup: standard Party Types on a clean test site** (CI, PR #168, merged with PR #169, 2026-11-09). ERPNext `version-16` (v16.54.0,
  `495380b`, 2026-11-06) now refuses a GL row whose party type has no Party Type record ("Supplier is not a valid
  Party Type"). The setup wizard creates these records on a real site, but the CI test site skips the wizard, so 118
  posting, reconciliation, catalog and period-lock tests failed on `main` and on every PR. The shared test masters
  (`_ensure_masters`, run committed by `card.install.before_tests`) now create the four standard Party Types
  (Customer, Supplier, Employee, Shareholder) when they are missing. Affected: `card/tests/test_controllers.py` only.
  Impact: tests only; no application code, schema, permission, accounting or API change; Production is not affected
  (its four Party Types exist, checked read-only 2026-11-09). Rollback: revert the commit.
- **Period-lock tests no longer depend on the calendar** (test-only, PR #158, Owner approval 2026-10-31). On main CI of
  `ef4f412` the test site's date was already the 1st of a month. `card/tests/test_period_lock_extra_keys.py`
  recorded hours on day 2 of the open month, and the card's future-day rule refused that day, so 4 tests failed
  (2 failures, 2 errors).
  - The tests now run on a fixed site date (Frappe `freeze_time`, mid-month).
  - Worked days are written only up to the frozen today.
  - Two new tests cover the 1st of a month: an open card keeps the cancel rules, and hours on day 2 are refused
    as a future day.
  - No application code, validation, period-lock rule, permission, data, accounting or API change. Rollback:
    revert the commit.
- **Monthly posting integrity, P0** (FR-090, PR #151, integration audit 2026-10-30; QA failures T3b, T3c, T9h2, T9h3, T9i).
  - *Edited drafts*: the builder stores a signature of every financially significant field of the draft
    (party, company, accounts, items, quantities, rates, projects, cost centers, Card Equipment, tax
    template and rows, discounts, descriptions). Submit refuses any difference. An Accounts Manager may
    accept a corrected cost center or expense/income account (same company, enabled leaf, same root type)
    with a reason (`card.gl.integrity.accept_correction`, POST); the acceptance is tied to that exact
    content. Drafts built before this change must be rebuilt before submit.
  - *Copies*: a Purchase/Sales Invoice that is not itself an active CARD posting cannot be submitted when
    it repeats the lines of a CARD posting (Desk "Duplicate") or names a CARD source that an active posting
    holds. A CARD posting may not reuse the supplier bill no. of another live invoice of the supplier.
  - *Hand-booked supplier invoices*: before building a supplier month, CARD lists the supplier's draft or
    submitted Purchase Invoices (not returns) that it did not build, dated (posting or bill date) from one
    month before to two months after the CARD month, with a line on any Expense account, a CARD account or
    a CARD item (lines without an item count by their account). The build is refused until each one is linked to the CARD sources it
    pays for (`card.gl.integrity.link_supplier_invoice`, POST, accountant roles: a Linked GL Posting Log
    reserves the sources; nothing is reposted and the invoice is not changed) or declared unrelated by an
    accountant (`reviewed_invoices` on `post_month` / `rebuild_month`, recorded on the log). Several
    legitimate invoices per supplier and month stay possible. Rebuild never deletes a linked invoice.
    A link never shows unmatched amounts as matched: the sources are compared with the invoice's net total
    on one VAT-exclusive basis (cards and transports net; diesel fills by the Diesel price VAT basis, net of
    VAT when it is Inclusive and the invoice carries VAT). A gap, or a basis that is not verified, needs an
    accountant's explicit acceptance with a reason and is stored on the log (`link_difference`). Sources may
    span several months. Linking needs an accountant role, the company in the caller's CARD and accounting
    scope, read on the supplier and the sources, and submit right on the invoice. An imported diesel session
    that carries a supplier invoice no. can be linked only to the invoice with that bill no. A hand-booked
    invoice submitted for a supplier that CARD posted for a nearby month shows those postings as a warning.
    A linked draft is re-checked at submit (same company and supplier, not a return, net equal to the linked
    sources plus the accepted difference); a source cannot be listed twice in one link; a hand-booked invoice
    cannot reuse the supplier bill no. of a CARD posting. The reconciliation counts a linked card in its own
    month and keeps the rest of a linked invoice (diesel, transport, difference) among the invoices outside Card. A linked source cannot be cancelled while the
    invoice stands; credit and debit notes against linked or CARD invoices stay allowed.
  - *Diesel VAT basis*: new Card Company Settings field `diesel_price_vat_basis` (Exclusive / Inclusive /
    empty). For a VAT-registered supplier, empty refuses the build for review; Inclusive books the net
    part (fill amount × 100 / (100 + VAT rate)) so the invoice total stays the fill amount; Exclusive keeps
    the earlier behaviour. Imported diesel sessions stay outside CARD posting (FR-086b).
  - *Concurrency*: sources are row-locked in a stable order and their reservation re-checked before the
    draft is written.
  - Impact: accounting controls only; no GL written by CARD; new fields on GL Posting Log and Card Company
    Settings (migrate). Permissions: two new POST endpoints with role checks (Accounts Manager for
    corrections; Accounts Manager / Accounts User for links and reviews). Rollback: revert the commit;
    the new columns stay unused.

### Migration

- **Patches:** none. `card/patches.txt` is unchanged since v4.2.2; `bench migrate` runs no CARD data patch.
- **DocType sync (new nullable columns, no value written to existing rows):**
  - Card Company Settings: `diesel_price_vat_basis` (Select, permlevel 1; empty on every existing company).
  - Card Equipment: `customer_rate_night` (Currency, permlevel 1; empty on every existing equipment).
  - Equipment Transport: `responsibility` (Select, mandatory), `payer`, `cost_bearer`, `cost_basis`,
    `customer_billable`, `supplier_recoverable`, `cost_project`, `overhead_cost_center`, `financial_status`,
    `submitted_by`, `edited_by`, and at permlevel 1 `financial_decision`, `customer`, `billing_project`,
    `billing_amount`, `billing_mode`, `billing_reference`, `billing_document`, `absorption_reason`,
    `recovery_mode`, `recovery_amount`, `decision_note`, `financial_approver`, `financial_decided_on`.
    `cost_borne_by` becomes read-only and loses its `Company` default; its stored values are kept.
  - GL Posting Log: `origin`, `built_signature`, `lines_signature`, `built_snapshot`, `accepted_signature`,
    `accepted_by`, `correction_reason`, `reviewed_invoices`, `link_difference`.
- **Field levels changed on Card Equipment** (metadata only, values unchanged): `cost_center`,
  `asset_cost_center`, `asset_purchase_value` 0 → 2; `internal_hourly_rate` 1 → 2; `approved_hourly_rate` 0 → 1.
- **Records synced:** four Script Reports (Diesel Invoice Reconciliation, Transport Accounting Review, Equipment
  Meter Reconciliation, Asset Mapping Review), the Report Print Format `Equipment Supplier Statement A4`, and the
  Card Reports sidebar links. New hook: Version `before_insert` (`card.field_privacy.mask_restricted_version`).
- **What migrate does not write:** no transport, card, fill, posting, GL Posting Log, Version or settings value;
  no `responsibility` / `payer` / `cost_bearer` on existing transports; no diesel VAT basis; no night rate; no GL
  entry; no role or DocPerm change.
- **Breaking changes — act on them after migrate:**
  1. *Equipment Transport* (FR-093): `responsibility` is required and `cost_borne_by` no longer defaults to
     Company. Draft transports saved under v4.2.2 need `responsibility` (or `payer` + `cost_bearer`) before their
     next save or submit. External or REST clients that create or save transports must send those fields; a v4.2.2
     payload (no responsibility, no payer) is refused. No patch fills them in. Submitted transports keep their
     `cost_borne_by` and stay readable as recorded.
  2. *Card Equipment field privacy* (FR-096, FR-097): Card User and Card Supervisor (and any other role without
     the level) no longer read `cost_center`, `asset_cost_center`, `asset_purchase_value` and
     `internal_hourly_rate` (now level 2: System Manager, Card Manager, Accounts Manager); Card Supervisor no longer
     reads `approved_hourly_rate` (now level 1). This applies to the form, REST API, list and report queries and
     exports; `card.api.get_asset_prefill` and `card.api.create_equipment_from_asset` return only the fields the
     user may read. Card User can no longer set the equipment cost center.
  3. *Posting integrity* (FR-090): posting drafts built before 4.3.0 must be rebuilt before submit (they carry no
     built signature). For a VAT-registered supplier, an empty `diesel_price_vat_basis` on Card Company Settings
     refuses the build: set Exclusive or Inclusive per company first.
  4. *Cost allocation* (FR-091): a build is refused when a cost center is missing, unusable (group, disabled,
     other company) or conflicting, and for every company-paid move to or from a project. Check the project and
     assignment cost centers before the first build.
- **Rollback:** see the v4.3.0 release page. Last stable version: v4.2.2. v4.2.2 code can run on the migrated
  schema after a `bench migrate` with that code (the new columns are nullable and stay unused; no patch wrote
  data), but whether it runs *safely* on data created
  under 4.3.0 is **Unknown**: v4.2.2 takes every submitted, not yet invoiced transport with an empty `cost_borne_by` into the
  transport supplier's monthly build as a company-paid move, and every transport saved under 4.3.0 has an empty `cost_borne_by`. The rollback is a
  restore of the pre-upgrade backup (only while no transaction was made after it) or a forward fix.

### Known limitations

- Published ≠ deployed: no site runs 4.3.0 yet.
- Transport (FR-093): customer transport invoicing, supplier recovery documents, Purchase Invoice posting of
  P1-2 transports, tax treatment and account mapping are disabled on purpose; the accountant enters the
  transporter's invoice for those moves.
- Posting (FR-004): the monthly build still has no Desk button.
- Existing Card Equipment Version records are not changed by FR-096 (they held no financial value on the checked
  site).
- The four new reports are read-only; the meter reconciliation sets no maintenance baseline; a diesel period
  difference is a point to review, not a confirmed over-billing.
- A4 supplier statement: Landscape must be chosen in the PDF dialog.
- Compatibility with ERPNext v16.54.0+ (Company Restriction) is shown by CI on the latest `version-16` only; no
  site with Company Restriction has been checked. The upgrade rehearsal ran on frappe 16.51.1 / ERPNext 16.50.0.

---

## [4.2.2] — 2026-10-27

### Changed
- **Diesel fill: meter photos shown large in place of the file link, clearer reading labels** (FR-088,
  Owner 2026-10-27). The opening and closing meter photos now show as a card in place of the file
  link, full width up to 480 px high, so the meter can be read without opening the file; a click
  opens the photo in a new tab. On an editable fill the card has the control's own change (image
  uploader) and remove (with its confirmation) buttons. Only a file of the site (`/files/...` or
  `/private/files/...`) is shown this way, and a private photo still needs read permission on the
  fill; any other value keeps the standard link. The standard Attach Image control shows only the
  file name, with a 150 px preview on hover. Arabic labels: "قراءة عداد التعبئة عند البداية" /
  "... عند النهاية" (the session meter that is reset at each fill, not the totalizer), and the two
  messages that name them. Functions: `project_diesel_fill.js` (`card_photo_previews`),
  `card/locale/ar.po`. Impact: display only; no schema, permission, accounting, data or API change.
  Rollback: revert the commit.

### Migration

No patch, no new column and no DocType change. Form script and Arabic translations only. Rollback: v4.2.1 code runs
on the same database; nothing to undo in data.

---

## [4.2.1] — 2026-10-27

### Changed
- **Simpler diesel fill form** (FR-087, Owner approval 2026-10-27). The `Project Diesel Fill` form opens with three
  sections: the fill (date, project, supplier; the company is filled and hidden for a user with one company, as on
  Equipment Transport), **Meter readings** (opening and closing photo and reading, then the litres; open, was the
  collapsed "Session evidence") and **Equipment filled** (the list and the direct-charge equipment). The price shows
  as one line (price per litre and amount); the company price is hidden (same value) and the price source shows
  only when it is not the company price. The evidence check shows only with a warning or an inconsistent
  totalizer; the operations review shows after the first save; the totalizers, photo times and place move to a
  collapsed **Meter details**; the price exception section shows only to the exception roles or on a fill that has
  one; the import fields show only on an imported fill (**Supplier invoice and source**); cost center and posting
  links move to a collapsed **Cost Center and posting**; remarks come last. Field help texts removed. Messages say
  "session import" instead of "WhatsApp import". Layout only: no field, column, permission, validation, price or
  posting change. Rollback: revert the commit. Translations: ar for the 4 new section labels.

### Migration

No new patch and no new column. `bench migrate` syncs the `Project Diesel Fill` DocType layout (field order,
sections, visibility). Rollback: v4.2.0 code runs on the same database; nothing to undo in data.

---

## [4.2.0] — 2026-10-27

### Added
- **Import of reviewed WhatsApp diesel sessions as draft fills** (FR-086, Owner 2026-10-26; builds on
  FR-085). New server function `card.diesel_import.import_sessions(manifest, photos_dir, dry_run=1)`,
  run by a Card Manager or System Manager with `bench execute` (not a web endpoint). Each session in
  the JSON manifest becomes a draft `Project Diesel Fill` with its opening/closing meter photos as
  private files attached to the fill; the photos must match the SHA-256 in the manifest and the
  photo names cannot leave the given folder. One fill per source key: new read-only fields
  `source_key` (unique), `source_messages` (message ids and the original photo SHA-256, since the
  site may strip EXIF on upload) and `source_caption` keep the source; only the import may set
  them (a form or REST save that sets or changes them is refused), and a re-run skips every key
  that exists in any state. The fill's own validation applies (readings give the litres,
  duplicate photos are refused, totalizer check, review status). The price is always the company
  price: a session without a price or with another price is refused. Reported equipment is kept as names only
  (match status Unmatched, no litres). The import never approves, submits or posts, and a failed
  session leaves no fill and no file. Dry run is the default and keeps nothing. Impact: no new
  permission, endpoint or accounting effect; schema: 3 new columns on `Project Diesel Fill`, no
  patch. Rollback: revert the commit; imported drafts stay until deleted by a manager. Tests:
  `card/tests/test_diesel_import.py`.
- **Historical price of imported diesel sessions** (FR-086b, Owner design approval 2026-10-27,
  option A). A session in the import manifest may carry its own supplier invoice (`invoice`: number,
  quantity, price per litre, delivery charge litres, file and SHA-256). The fill then keeps the
  invoice price instead of the current company price and waits as `Needs Review`. Only the price
  exception role (Card Settings) approves it with the existing price exception and a reason; there
  is no automatic price approval, and a Card Manager cannot change the price. The exception role
  cannot move it to the company price either; removing its exception returns it to the invoice
  price as Needs Review. An amendment keeps the source and invoice evidence of its original (the
  unique `source_key` stays with the original) and stays out of the posting; only a real amendment
  inherits it (cancelled original of the same company, amend permission, the only live amendment;
  security review SR-1). New read-only
  evidence fields on `Project Diesel Fill`: `supplier_invoice_no`, `invoiced_litres`,
  `invoice_unit_price`, `delivery_charge_litres`, `invoice_evidence`; only the import sets them. The
  litres and the amount stay the meter's: the delivery charge billed as litres is evidence only.
  The monthly posting (`card/gl/posting.py`) now leaves out every imported fill and its amendments (`source_key` or `source_messages` set):
  its supplier's own invoice is the Purchase Invoice, and its price includes VAT. Impact: no new
  permission or endpoint; accounting: imported fills are never posted by CARD; schema: 5 new
  columns, no patch. Rollback: revert the commit. Tests: `card/tests/test_diesel_import.py`,
  `card/tests/test_s3_posting.py`.
- **Diesel fill as a metered session with evidence and an operations review** (FR-085, Owner Phase 1
  approval 2026-10-26). `Project Diesel Fill` gets opening/closing meter photos, readings,
  totalizer readings and photo times; when a closing reading is given, the litres are
  `closing − opening`. A totalizer check (Not Checkable / Consistent / Inconsistent) compares the
  session with the meter's cumulative counter: exact readings may differ by 1 litre (measured on
  real photos), and an unreadable last drum widens the range by its own 0–9 digit only. It is
  advisory and never approves a fill. Meter photos must be private files uploaded to the fill
  itself (on an unsaved form: the uploader's own file under the form's temporary name; a
  client-sent temporary name of another record is ignored). The same photo (same file or same
  bytes) cannot prove two live fills; a rejected fill releases its photo, and a fill of another
  company is never named. A second fill on the same project and day is
  allowed with a warning. New child table `Diesel Fill Equipment` lists the filled equipment
  (equipment, name as reported, match status, notes) **without litres**; it is exclusive with
  the single `card_equipment`, and the diesel allocation and posting ignore it. Allocation stays
  recorded (one equipment) or estimated (hours split). New operations review: `review_status`
  (Draft / Needs Review / Operations Approved / Rejected, permlevel 1). Only Card Manager or
  System Manager approve or reject it; approval needs the closing photo and reading; the reviewer
  and time are set on the server; a material edit after approval (litres, readings, photos,
  totalizers, company, project, date, supplier, equipment, cost center or the equipment list)
  returns the fill to Needs Review.
  **Behaviour change:** submit now needs Operations Approved (before: any valid fill could be
  submitted by Card Manager). Impact: new permlevel-1 DocPerm rows on `Project Diesel Fill`
  (Card Manager and System Manager write; Card User and Accounts Manager read); no change to the
  price lock, allocation, posting, accounting or API; schema: 15 new columns + 1 child table, no
  patch. Existing fills keep their data, and submitted fills are never re-validated. Rollback:
  revert the merge commit. The new columns stay in the database until removed by hand. Tests:
  `test_diesel_session_evidence.py` (new), `test_diesel_allocation.py`
  (`test_listed_equipment_never_counts_as_recorded`), and the existing fill tests approve before
  submit (`card/tests/diesel_price.py::approve_fill`).
- **Parts fitment in the catalog search, catalog phase 2b (FR-078; Owner decisions A–D, 2026-10-23; PR #110)**: the catalog
  shows each Item's fit for a chosen machine, in four separate states: Confirmed (for this machine, or for its
  model), Not compatible (warning), Pending technical review, and No fitment record. The machine's decided row wins
  over its model's; a pending row is never a fit (O6). "Fits this machine" lists only confirmed fits, filtered and
  paged on the server; Not compatible items stay in the normal search with a warning. New GET endpoints
  `card.fitment.fit_for` (up to 50 Items) and `card.fitment.machines` (machines the caller may use);
  `card.catalog.search` takes `equipment` and `fits` (unchanged answer without them). A machine is used only by a
  user who may read it (DocPerms, User Permissions, company isolation) or by its own operator. Results carry the fit
  and the model name only, never evidence, reasons, reviewers or notes (Q8). **Card User** opens CARD Mobile as a
  read-only catalog viewer (decision A): the new Catalog page and his profile only, no Employee needed; request
  endpoints still refuse him, and he still has no access to fitment rows. Request lines (Q10, decisions C and D):
  `Equipment Needs Request Item` gets `fit_status` (read only) and `fit_reason`; at submit every picked Item without
  a confirmed fit needs the reason (CARD Mobile, the older `/equipment-needs` page and Desk); the review line shows
  both. Proposals stay in Desk (decision B). Nothing in search, requests or reviews changes a fitment row (Q6).
  Translations: ar for all new strings, bn / hi / ur for the operator strings. Impact: two new columns on each of
  `Equipment Needs Request Item` and `Equipment Needs Review Item` (DocType sync); Card User gets CARD Mobile catalog
  access (Owner decision A); no ERPNext DocType, role or permission change; no data patch; no accounting change.
  Rollback: revert the merge; the new columns stay (empty or kept); Card User loses the catalog page.

### Fixed
- **An equipment assignment can no longer stop covering a submitted card day** (found in the
  2026-10-26 backlog triage, #43). Submitting an Equipment Transport ends the machine's open
  project assignment on the transport date; a backdated transport, or a manual edit of the
  assignment (later start, earlier end, other project or equipment, delete), left the submitted
  card days of that project outside every assignment, for the machine and for a unit card that
  lists it as a component (only the transport cancel path checked card days). The save is now
  refused and names the card and the day (`CardEquipmentAssignment.validate` / `on_trash`,
  `_refuse_dropped_card_days`; the machine row lock of D4 and a locking read). A transport on or
  after the last submitted card day is unchanged. No data, permission, accounting or API change;
  existing assignments are not rechecked. Known limit: a card submitted at the same moment as the
  transport is not locked against it (card validation reads assignments without a lock).
  Rollback: revert the merge commit. Tests: `test_transfer.py` (3 new).
- **The application name is CARD in every language** (WS-013, Owner decision 2026-10-26). The record
  names stay `Card` (frappe names the Workspace, Workspace Sidebar and Desktop Icon after their
  label, so a rename would break `/app/card`); the display name comes from translations instead:
  msgid `Card` maps to `CARD` in every CARD locale, and CARD now ships a locale with that one entry
  for each of the other 38 languages frappe translates (before, for example, fr showed "Carte" and
  fa "کارت"). The apps screen titles are `CARD` and `CARD Mobile`, and the
  CARD group in the Supplier, Customer, Asset and Project connections shows `CARD`.
  Patch `v4_1_3.remove_app_name_translations` removes the site `Translation` rows whose source text
  is exactly `Card` with no context (for example ar `Card` -> `كارت`), which override the app's
  locale files; every other Translation stays, and frappe keeps each removed row as a Deleted
  Document. Idempotent. Tests: `test_i18n.py::TestCardNameNotTranslated`,
  `test_app_name_translation_patch.py`.
  Impact: no permission, accounting, API or schema change. The frappe field label "Card" (Number
  Card Link) uses the same msgid and also shows `CARD`. Rollback: the previous release restores the
  old locale files; a removed Translation can be restored from its Deleted Document.

### Migration

One new patch, `card.patches.v4_1_3.remove_app_name_translations` (removes only the site `Translation`
rows whose source text is exactly `Card` with no context; frappe keeps each as a Deleted Document;
idempotent). DocType sync adds: 23 columns on `Project Diesel Fill` (session evidence, operations
review, import source with a unique `source_key`, supplier invoice fields), the new child table
`Diesel Fill Equipment`, and `fit_status` / `fit_reason` on `Equipment Needs Request Item` and
`Equipment Needs Review Item`. No data is rewritten: existing diesel fills keep their values and get
review status Draft by the column default. Behaviour change: a diesel fill now needs Operations
Approved (Card Manager or System Manager) before submit. Rollback: v4.1.2 code runs on the migrated
database (the new columns and the child table are ignored by it); a removed Translation can be
restored from its Deleted Document, or restore the pre-upgrade backup.

---

## [4.1.2] — 2026-10-25

### Fixed

- **CARD launcher shows all its sections again.** frappe 16 lays a site's `Dock` layer over the
  app's dock, and a saved layer is the whole rail: entries an app ships later are not added to it
  (`frappe/desk/doctype/dock/dock.py`, `resolve_app_dock`, `keep_unnamed=False`). A site layer saved
  before v3.0.0 (on production: 2026-10-13, one entry) hid nine of the ten launcher entries, so
  the dock rail showed one entry ("Card (Custom)") and `/desk/card` only the dashboard sidebar (Card,
  Card Monthly Card, Equipment Transport).
  `card.navigation.restore_launcher_entries` (run after every migrate) appends the missing entries,
  in the shipped order, to every non-standard CARD `Dock` layer last saved before the shipped dock
  file, so entries added by later releases also reach such layers. Existing rows, their
  order and hidden flags are kept; nothing is deleted; a layer saved later is not touched. Reach is
  unchanged: frappe still hides an entry the user may not open. No permission change.
- **Equipment Transport form is simpler.** Order: ownership → equipment supplier → equipment table →
  Route (current place, read-only, shown once known; destination) → Cost and date (transport cost,
  cost borne by, transport supplier, cost center shown once set, date, method, company, remarks).
  The system links (created/previous assignment, Purchase Invoice, GL posting, posted, amended from)
  move to a collapsible **Linked Records** section that appears only once one of them is set or the
  transport is submitted. The company is filled and hidden when the user has only one company; it
  stays visible and required with several. `card.company.only_visible_company` now also accepts the
  `select` permission on Company (what a link field needs), so a Card Manager without Company read
  gets the company filled too; it lists only the companies frappe already lets the user pick. Ownership and, for rented equipment, the equipment
  supplier are taken from the first machine when left empty; values the user picked are kept.
  Controller, transfer and accounting logic unchanged.
- **English error messages no longer contain Arabic.** List separators are translatable
  (`, ` / `; `, Arabic `، ` / `؛ `) and the shift value in the shift-limit message is translated.
- **English users no longer see Arabic stored values.** Stored Select values (ownership, rate type,
  shift, day status, statuses, directions, adjustment kind, diesel policy) and the Arabic-named
  workspace number cards, charts, shortcuts and section headers get English translations in `en.po`; `bn.po`, `hi.po` and `ur.po`
  carry the same English text, so these languages fall back to English, never to Arabic. Stored data
  is unchanged (display translation only).
- **Arabic users: 47 CARD strings that had no Arabic translation now have one** (descriptions,
  GL Posting Log fields, linked-record labels, report columns). Generic words (Item, Owner, Posted,
  Cost, ...) are scoped with `msgctxt` to the CARD DocType or the `Card` context so they never
  change ERPNext screens; the report columns and one button pass `context="Card"`.

### Added

- Tests: `test_launcher_restore` (the production layer shape, old layer restored in order, rows and
  hidden flags kept, newer layer untouched, idempotent), `test_transport_ownership_default`, and the i18n guard
  `TestNoArabicFallback` (every Arabic value shown on screen has a non-Arabic translation in
  en/bn/hi/ur).

### Migration

No new patch. A new `after_migrate` hook, `card.navigation.restore_launcher_entries`, writes only
non-standard `Dock` layers of the app `card` older than the shipped dock file; once saved, a layer
is newer than the file, so later migrates write nothing until a newer dock file ships. Rollback: the previous
version runs on the migrated data; to undo the navigation change, remove the appended rows from the
site's dock layer (Manage Dock) or restore the pre-upgrade backup.

### Known limitations

- Stored Arabic values show in Arabic for languages that CARD ships no locale for (any language
  other than ar, en, bn, hi, ur) and wherever frappe shows a raw value without translating it (for
  example a Data field, list filters typed by hand, exports). Print formats are Arabic by design.
- The monthly card's day names (`day_name`) are stored Arabic text in a Data field and are not
  translated.
- The launcher (dock) tooltips show each entry's stored title untranslated in every language
  ("Card Fleet", and on production the site's own "Card (Custom)"): frappe 16.51.1 draws
  `row.title` without `__()` (`frappe/public/js/frappe/ui/sidebar/sidebar.js`, line 984). Not
  changeable from the app without editing core.
- Otherwise the same as v4.1.1.

---

## [4.1.1] — 2026-10-25

### Fixed

- **Tool Custody screen: item search works without an ERPNext Item read permission (this PR).**
  Card Manager and other Tool Custody screen roles could not search for items in the New Handover
  dialog or the page filter because those Link fields used the standard Frappe link search, which
  requires `select: 1` on the `Item` DocType. Added a scoped `item_query` endpoint
  (`card.tool_custody.item_query`, GET) that returns stock items (non-fixed-asset, enabled) using
  `ignore_permissions=True` after `_check_screen()` confirms the caller holds a screen role and can
  read Employee Tool Custody. The JS link fields now use this endpoint instead of plain filters.
  The Stock Manager confirmation boundary (Stock Entry submit) and all other screen permissions are
  unchanged. No DocPerm change; no data change.

### Migration

No migration required. No new patches.

### Known limitations

Same as v4.1.0.

---

## [4.1.0] — 2026-10-25

> First production go-live release candidate (issue #118, phases P1–P3: equipment registration, transport,
> project assignment). Everything merged since v4.0.0.

### Added
- **Upgrade rehearsal in CI (go-live P0 #119, Owner decision D2; tooling only).** New workflow
  `upgrade-rehearsal.yml` (pull requests that touch patches, DocType JSON, fixtures, install or hooks, and manual
  runs): a site on the production frappe 16.51.1 / erpnext 16.50.0 gets CARD v1.0.1 and synthetic data shaped like a
  site in use (3 rented machines, 3 assignments, 5 monthly cards incl. cancelled and amended ones), is upgraded to
  the code under test, migrated twice and compared: every kept record and amount unchanged, no ledger, invoice,
  stock or Material Request document created, no transport invented, no Card role given, every patch ran once, the
  second migrate changes nothing; then legacy machines save, submitted cards load and a first transport submits
  (rolled back). Evidence is the run's `upgrade-rehearsal` artifact. No app code, data or permission change.
- **Equipment chassis and plate numbers are unique per company (FR-080, go-live P1 #120, Owner decision D1).** A
  Card Equipment refuses a chassis number (`serial_no`) or plate number (`plate_no`) that another equipment of the
  same company already uses. Numbers are compared without case, spaces, `- _ / .` or invisible marks (Unicode NFKC),
  with Arabic-Indic digits read as ASCII (new hidden fields `serial_no_key`, `plate_no_key`, indexed with the
  company); empty numbers are never compared; another company may use the same number. The check runs on the server
  (Desk, REST, imports) when the number is set or changed or the company changes, under a CARD lock per company
  (MariaDB named lock; no ERPNext row is locked) and a locking read, so two saves at once keep one equipment. The
  message names the other equipment only to a user who may read it. "Duplicate" no longer copies the two numbers.
  - **Migration:** patch `card.patches.v4_1_0.backfill_equipment_identity_keys` fills the two keys of existing
    equipment (no `modified` change, no Version) and lists numbers that existing equipment already share in the
    Error Log; those records are kept unchanged, an unrelated save of them is allowed, and their number can be
    corrected.
  - No role, DocPerm, setting, accounting or API change. Rollback: revert; the two key columns stay unused.
  - **Fix:** backfill patch passes `page_length=0` so all equipment records are processed, not only the first 20
    (Frappe v16 default page length).
- **Tool Custody screen (issue #113, PR-T3; Owner decisions U-1 to U-5, 2026-10-23).** A new Desk page
  `tool-custody` ("Tool Custody", Card Materials sidebar, before Employee Tool Custody) puts awaiting handovers,
  held tools and history in one responsive screen (desktop, tablet and phone; Arabic right-to-left), with employee
  and tool filters and server paging (25 rows).
  - **Who:** Card Supervisor, Card Manager, Stock Manager and System Manager with custody read (U-3). Card User and
    Card Operator do not see the page or its sidebar row. Default tab by role (U-5): the store side and Card Manager
    start on Awaiting, a supervisor on Held tools; every permitted user can switch tabs.
  - **Actions:** each row shows only the actions the server allows for this user (confirm, not handed over, new
    handover for the rest, return, transfer); the worker gets no action on own custody, and the approver or
    requester of a line cannot confirm it (same rule as the controller, now one function `confirmer_excluded`).
    Confirm is one dialog: quantity, Serial No when the item needs it, Print receipt, signed receipt attachment
    (Handover / Transfer), then the standard Submit with all controller rules. New Handover / Return / Transfer
    drafts fill their defaults (Card Settings store; for a Handover the worker's machine and its project).
  - **Stock (U-4):** the Awaiting tab shows the store quantity read with the user's own ERPNext rights (no figure
    without stock read); confirmation checks the stock again in ERPNext.
  - **Receipt (U-2):** standard print format "Tool Handover Receipt" for Employee Tool Custody: employee, item,
    quantity, equipment / project, issuer, receiver, date and two signature lines; right-to-left in Arabic.
  - **Searches without extra permissions (Owner, 2026-10-24):** the Employee and Store fields of the screen use its
    own Link searches `card.tool_custody.employee_query` and `store_query` (GET): active employees (the page filter
    also finds those who left) and enabled, non-group stores of the companies the user may see for custody, limited
    further by User Permissions on Employee or Warehouse; name and title only, for the screen roles only. The screen
    roles need no Employee or Warehouse read, and none was granted. The rows carry what the dialogs need (Serial No
    flag, receiver name), so the dialogs read no Item or Employee either. Return and Transfer dialogs say whose tool
    it is, which tool and how many are held; a Transfer shows "giver → receiver" in Awaiting, History and the confirm
    dialog.
  - Endpoints `card.tool_custody.context`, `view`, `employee_query` and `store_query` (GET, read only) and `confirm`
    and `move` (POST); custody reads go through `frappe.get_list` (DocPerms and Company User Permissions), writes
    through Employee Tool Custody with the user's own rights. No role, permission, DocType or accounting change; no
    data patch. The review approve message now says that tools wait for the store. Arabic translations for the new
    CARD strings.
  - Known limits: worker digital acknowledgment (T11) is a later phase; a receipt printed before confirmation names
    the person who printed it as issuer; Held totals count only the movements the user may read (the server checks the
    full balance on Return and Transfer); the Held tab reads all submitted movements before paging; the employee and
    store searches apply User Permissions on Company, Employee and Warehouse only (saving still checks the custody
    permissions); the open-record arrow of the Employee and Store fields needs read on those records. Rollback: revert
    the merge (the page, print format and sidebar row stay on a migrated site until removed by hand).
- **Parts fitment, catalog phase 2a (FR-077; Owner decisions Q1–Q11, 2026-10-23)**: which ERPNext Item fits which
  machine. New masters `Card Equipment Make` (CMK-) and `Card Equipment Model` (CEM-, one make and one equipment
  type); a normalised unique key refuses the same make or model written twice ("PC200-8" = "pc 200 8"), also when
  two users save at the same moment. ERPNext Manufacturer (the part maker of Item Manufacturer) is not used for
  machines. Card Equipment gets `equipment_make` and `equipment_model` (permlevel 1: Card Manager writes); the model
  must belong to the machine's make and equipment type; the free-text Brand / Model fields stay as they are and
  nothing is copied. New `Card Equipment Part` (CFP-): a fitment row on an equipment model or on one machine, with
  the DESIGN v4.1 states Pending Technical Review / Confirmed / Not Compatible, evidence source and reference, a
  private evidence file, quantity per use and technical notes. Every new row starts pending; status and audit fields
  are written by the server only (form, REST, `frappe.client`, import). Card Supervisor proposes and documents own
  pending rows; Card Manager or System Manager decides with evidence. **No final self-approval**: a decision by the
  row's proposer (Administrator included) is stored as a first review with reason and evidence file and the row stays
  pending (Pending Second Review) until another Card Manager or System Manager decides. A machine row Confirmed
  against its model's Not Compatible row needs technical notes. Rows are retired with a reason, never deleted; a
  restored row is reviewed again; history in the Version log. Machine rows follow the machine's company (permission
  query and document check); model rows are technical data without a company. Card User and Card Operator get no
  access to fitment rows or evidence files (the search view comes in phase 2b). Read-only Script Report
  "Equipment Make Model Values" (Card Manager, System Manager) lists the free-text brand / model values for manual
  set-up. Card Materials sidebar: Equipment Makes, Equipment Models, Parts Fitment and the report (shown only to
  users whose role may open it). Connections on Card Equipment,
  make and model. Arabic translations for the new CARD strings; generic words keep the Frappe / ERPNext
  translation. Impact: three new DocTypes and two new columns on Card Equipment, created by the DocType sync; no
  data patch; no ERPNext DocType, role or permission change; no accounting or API change (no new whitelisted
  method). Rollback: revert the merge; the new tables and columns stay (empty or kept); no data is deleted.
- **Catalog search (FR-076, phase 1 of the catalog; Owner 2026-10-22)**: CARD Mobile's item picker gets a
  "Browse catalog" dialog over the standard ERPNext catalogue (Item, Item Group, Brand, Item Barcode, Item
  Manufacturer, Item Alternative); CARD adds no item master and no DocType. Search by item name, item code, barcode
  or OEM part number; filter by item group (with its sub-groups) and brand; item image, OEM numbers and the
  standard alternatives (one-way, or both ways when `two_way` is set; pick an alternative directly); server paging
  with "Load more" (no total count). New GET endpoints `card.catalog.search` and `card.catalog.filter_options`
  (reads only). Permissions on the server: a user whose roles read Item gets `frappe.get_list` (his roles, User
  Permissions and rules apply); a Card portal role without Item read (Card Operator, the G1 exception of
  `search_items`, widened by Owner decision D-1 to OEM numbers and alternatives) gets the same item rules with his
  User Permissions (on the record and on every Link field, as `frappe.get_list` applies them) and shares; a test
  compares this read with `frappe.get_list` for the same User Permissions. The restricted read is only for Card
  portal roles: any other user without read on Brand, Item Group, Item Manufacturer or Item Alternative gets none of
  them, and the restricted read returns nothing where Frappe would add permission query rules CARD cannot apply.
  Barcode matches run inside the item query and OEM matches through the same permission path as the OEM numbers
  shown, without a cap, so a hidden item is never found or counted and a visible one is never crowded out. No
  stock, price, supplier or account is returned (the stock hint stays F2-only);
  private image files keep their own access (a placeholder shows when the image cannot load). English UI strings
  with ar, bn, hi and ur translations under the context "Card Mobile"; Item Group names are translated by Frappe,
  item names and brands show as entered. Desk: a "Catalog" row in the Card Materials sidebar opens the standard
  Item list (image view and filters are standard); no Workspace, fixture, role or permission change; its label is
  translated in ar only, like the other Desk labels of CARD.
  `card.materials.search_items` (the inline suggestions of `/cdms` and `/equipment-needs`) now uses the same rules
  and rights (it also matches barcodes and OEM numbers, hides ended items and keeps `%`/`_` literal).
  Data, schema and accounting: no change. (#106, merge `c0ee350`; FR-076 phase 1 only. Not released or deployed;
  target: next release. Real ERPNext integration in a browser not verified.)
  Rollback: revert the merge; the next `migrate` removes the sidebar row; nothing else to clean up.
- **CARD Mobile at `/cdms` — foundation** (planned for v4.1.0): a phone-only Progressive Web App served by CARD
  itself, built like the Frappe HR mobile app (Vue 3, TypeScript, frappe-ui in `frontend/`, built by
  `bench build` into `card/public/frontend` and `card/www/cdms.html`). In-app sign-in with the
  user's ERPNext account (Frappe session and CSRF); the user needs a CARD portal role and an
  Active Employee. Operator screens: Home (machines, open requests), New request, My requests,
  Profile; they call the existing operator endpoints (`get_portal_context`, `search_items`,
  `submit_needs`) and add no business logic. On a computer the same phone UI shows in a centered
  480 px column. Installable: web app manifest with maskable icons, Apple touch icon and iOS meta,
  safe areas; the service worker is served at `/cdms/sw.js` (scope `/cdms/`, `page_renderer`
  hook). Arabic and Urdu right-to-left; English, Bengali and Hindi. Generic words carry the
  translation context "Card Mobile", so they never override Frappe or ERPNext translations.
  Real iPhone and Android installation is **not yet tested**.
- GET `card.mobile.get_session_context` (the signed-in user's CARD Mobile context; reads only).
- **Diesel price lock per company (FR-002)**: a Project Diesel Fill takes its price per litre from the
  company's row in Card Settings and users cannot type another one. No new fill is saved without an approved
  price. A price exception needs the role in Card Settings `diesel_price_exception_role` (default Accounts
  Manager) plus write rights on the fill, and a mandatory reason; the fill keeps the company price it replaced,
  who approved it and when (also in the Version log). A zero price needs `diesel_zero_price_role` (empty by
  default = nobody). Submitted and cancelled fills are never repriced, and a saved draft keeps its price when
  the company price changes (it only shows the current price); a new company price applies to new fills only.
  Drafts saved before this change keep their price and, when it differs from the company price, wait for an
  explicit choice before submit. Every change of a saved draft's price (setting or changing an exception,
  "Remove price exception", "Use company price") needs the exception role and a written reason; the server
  records the old and new price, the user, the time and the reason (comment, Version and log). A plain save or
  a REST call cannot end an exception. No data patch: existing rows are unchanged.
- **Codecov coverage upload (CI only):** CI already measured coverage but nobody could see it. The "CARD unit
  tests" job now uploads the report that `run-tests --coverage` writes (`sites/coverage.xml`) to Codecov with
  `codecov/codecov-action@v5` and the `CODECOV_TOKEN` repository secret, so each pull request shows its coverage.
  A failed upload does not fail the job (`fail_ci_if_error: false`). The new `codecov.yml` makes the Codecov
  statuses informational only. It also keeps `tests/`, `test_*.py` and `patches/` out of the report (Frappe already
  omits some of these paths). No app code, permission, accounting, data or API change. (#93) Rollback: revert the
  merge.
- **Codecov coverage badge (documentation only):** `README.md` shows the Codecov coverage badge next to the CI and
  release badges, so readers see the Python test coverage of `main` (CARD Mobile `frontend/` is not measured). The
  repository is public, so the badge URL has no token.
  No app code, permission, accounting, data or API change. (#94) Rollback: revert the merge.
- **Security tests for the coverage program, Batch 1a (tests only):** new and stronger tests for the Asset link
  endpoints (`get_asset_prefill`, `create_equipment_from_asset`, `available_assets_query`) and the equipment Asset
  link, `get_shift_heatmap`, `get_equipment_location`, `refresh_supplier` / `refresh_customer`, `party_figures`,
  `get_card_diesel`, the company scoping of assignments, registries, party and diesel-fill link queries, the monthly
  card company guard, the operator request rules and the operator page guest redirect. Each deny has a permitted
  control. The Asset tests build their own fixtures, so they run in CI instead of skipping. `card/install.py`:
  `before_install` / `after_install` are excluded from coverage (`# pragma: no cover`) because they run at
  `install-app`, before coverage measurement starts. No behaviour, permission, accounting, data or API change.
  (#96) Rollback: revert the merge.

### Changed
- **Tool handover confirmation (issue #113, PR-T2; Owner decisions T1, T2, T2b, T5–T9, H-1–H-3, H-5–H-7,
  2026-10-23).** Management approval and the physical handover are now separate steps:
  - **Approval** (`card.materials.approve_review`) of a Tool line makes a draft Employee Tool Custody Handover for the
    request's worker, with the item, approved qty, line warehouse, project and equipment, linked to the review line.
    It is "Awaiting handover": it moves no stock and counts for nobody. A tool from the store gets no Material
    Request any more (before: a draft Material Transfer MR, and a second move by the custody record). A bought tool
    keeps its Purchase MR and gets the same draft. The approver also needs create permission on custody records.
  - **Confirmation** is the standard Submit of the custody record, by the store side. For a Handover or a Return
    the Stock Entry store ↔ custody store is inserted **and submitted** in the same transaction, with the
    confirmer's own ERPNext rights. ERPNext refuses a store without stock and the whole confirmation rolls back.
    So the confirmer needs custody submit **and** Stock Entry submit permission (Stock Manager, or a Card Supervisor
    / Card Manager who also has Stock User). No role or permission was added (T2b, H-5).
  - **Evidence:** a Handover and a Transfer need a signed receipt (`handover_receipt`): a private file uploaded to the
    record, signed by the receiving employee and the issuer (H-1, H-3). CARD records that the file was attached; it
    does not verify signatures. `handed_by` / `handed_on` record who confirmed and when.
  - **The signed receipt stays private and on its record** (`card.custody_receipt`, File hooks `before_validate` and
    `before_insert`; Employee Tool Custody `protect_attached_files`). Frappe shares one disk file and URL between
    File rows with the same bytes, and making any of them public makes all of them public. A file's owner can also
    make it public or delete it. Found by a probe on an isolated copy: the uploader could publish the receipt to
    Guest or delete it, and a reader could re-upload the downloaded bytes onto the receipt's file. Now the
    receipt, and any file that shares its content or URL, cannot become public; no second File row may carry its
    content or URL outside a custody record that names it (an Amend, or the uploader reusing one signed scan for
    several of his drafts), and no public copy at all; a receipt cannot be detached from its record (its owner can
    edit the File's attached_to fields); and a receipt of a confirmed or cancelled record cannot be deleted (a
    cancelled movement with a receipt is not deletable either: Frappe removes the disk file inside File.on_trash,
    so only its earlier permission check can keep it; Administrator, whom Frappe does not check, is the exception). A file
    is a receipt when a custody record names its URL in `handover_receipt` (the record decides, not the File row);
    other attachments keep Frappe's behaviour. An unattached file counts as the receipt only when the user uploaded it
    after the record was made (not an old scan). Other files
    keep Frappe's behaviour. No Frappe setting or core change. Limit: a user who may read the receipt can still
    save it and share it outside CARD; a copy that Frappe rebuilds from decoded text is a separate file.
  - **Date:** a confirmed Handover or Return is dated the day it is confirmed, the day its Stock Entry posts.
  - **Amend** only a cancelled movement of the same company that the user may amend (an amendment copies the
    attachments of the record it amends); `amended_from` never changes on an existing record. A receipt's File
    row keeps its URL, and no file sharing a receipt's content changes its public / private state (Frappe would
    change it, and the URL, on every row with that content).
  - **One tool leaves custody once:** a Return, Transfer, Loss or Damage takes a row lock on the worker and reads
    the balance again with a locking read, so two movements at the same moment cannot take the same tool twice.
  - **Reviewed drafts:** the store side may choose another store of the company and lower the quantity; the
    quantity is checked against the approved rest also when a draft is saved.
  - **Separation of duties** (server): the worker(s), the requester, the user who entered the request for the
    worker and the approver of the review cannot confirm. Administrator is not exempt (H-6).
  - **No double handover:** the custody row and the review line are locked during the confirmation. The quantity
    is checked against approved minus handed. A partial confirmation leaves a new draft for the rest (T6). The
    review links, the status and the confirmation fields are written by the server only.
  - **Failed handover:** `card.materials.close_tool_handover` (POST; store side or Card Manager) closes a waiting
    draft as "Not handed over" with a mandatory reason. The draft is then read only and never submitted.
    `card.materials.make_tool_handover` (POST; Card Manager only, H-2) makes a replacement draft for the rest of the
    line. It refuses a line approved before this change, because that line's Material Transfer MR already moved the
    tools. The worker cannot close their own handover. A reviewed handover cannot be deleted or amended. Desk buttons
    for these two actions come with PR-T3.
  - **Cancel:** cancelling a Handover or Return confirmed this way cancels its own submitted Stock Entry in the same
    transaction (ERPNext refuses to cancel an entry while a submitted custody record links it) and gives the qty back
    to the review line. The user needs Stock Entry cancel permission. An older record keeps "cancel the Stock Entry
    first". Known limit, unchanged by this PR: when the stock team has submitted that older entry, neither can be
    cancelled from the app.
  - **Unchanged:** Loss and Damage (draft Material Issue for the stock team; their approval comes in a separate PR,
    H-4), custody reports and Part lines.

  Effect on supervisors today: a Card Supervisor can still create and edit custody drafts of every movement. Without
  Stock User they can no longer submit a Handover or a Return themselves (the store side confirms). A Handover or
  Transfer also needs the signed receipt, and nobody confirms a movement of their own custody.

  Existing data (H-7): no patch and no data change. Open tool Material Transfer MRs stay for the stock team to close.
  On the dev site there are no custody records and no such MRs. Production was not inspected (needs a separate
  read-only approval).

  New fields: Employee Tool Custody `handover_status`, `handover_receipt`, `not_handed_reason`, `handed_by`,
  `handed_on`, `review`, `review_item`; Equipment Needs Review Item `tool_custody`, `handed_qty` (the DocType sync adds
  them). Arabic translations for the new CARD strings.

  Tests: `test_v4_materials` (approval drafts, store-side confirmation with a submitted entry, supervisor without
  stock rights, separation of duties, partial, store without stock rolled back, bought tool, closed and replaced
  handover, server-only fields, cancel, return and transfer with evidence, receipt file rules, other-company user;
  a cancel refused while later transfers or returns use the tools, or while the tools are no longer in the custody
  store (ERPNext refuses the reverse move, everything rolls back); cancel of a partial handover; who can open the
  signed receipt)
  and `test_tool_handover_concurrency` (two database connections: one replacement draft, one transfer).

  Rollback: reverting the code leaves the new columns empty and harmless. Custody records confirmed with this version
  keep their submitted Stock Entries; drafts made by approvals stay drafts (close or delete them by hand after a
  revert).
- **Go-live priority rule (documentation only):** `AGENTS.md` has a new "Go-live priority" section. Issue #118 sets
  the order of release work (P0 to P8); work stays on the current phase, optional improvements go to the backlog,
  and a phase closes only after real use is accepted (CI, merge or QA is not LIVE). The existing approval ladder,
  backup and rollback rules are unchanged. No code, data, permission, accounting or API change. Rollback: revert
  the commit (documents only, nothing to restore).
- **Agent skills rule (documentation only):** `AGENTS.md` has a new "Skills" section. Before each development or
  review task, an agent loads the official Frappe skills that fit the task with its Skill tool (`frappe-ui` for CARD
  Mobile), records them under `SKILLS_LOADED` in its report, and stops with `SKILL NOT FOUND` when a required skill
  is missing. Reason: agents that start inside the repository did not see this rule. No code, data, permission,
  accounting or API change. Rollback: revert the commit (documents only, nothing to restore).
- **CARD Mobile Home: the equipment list uses the frappe-ui `List` family** (`frontend/src/pages/Home.vue`;
  `List`, `ListRows`, `ListRow`, `ListCell` from `frappe-ui/list`, frappe-ui 1.0.2 as before). Reason: first step of
  the incremental adoption of official frappe-ui components in CARD Mobile. Same data in each row (equipment name or
  code, project), not clickable as before. Look: rows are at least 68 px and grow with large fonts; the dividers start
  at the text, not at the icon. No change to
  permissions, accounting, data, prices, the API or the server. Rollback: revert the commit (frontend only; a new
  `bench build` is needed on a site that ran it).
- **Change, versioning and rollback policy (documentation only; target: next release):** new binding
  [Change, Versioning & Safe Rollback Policy](docs/governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md) (commits,
  CHANGELOG and Feature Registry duties, SemVer and release requirements, safe rollback, task closing, approval
  ladder), a public [deployment record](docs/releases/DEPLOYMENTS.md) (versions only), and `AGENTS.md` /
  `CLAUDE.md` at the repository root so agents find the rules. Pointers added to RELEASE-POLICY.md,
  FEATURE-REGISTRY.md and CONTRIBUTING.md. No code, data, permission, accounting or API change; no past tag or
  release changed. Rollback: revert the commit (documents only, nothing to restore).
- **Card Settings layout (simplified):** the diesel price per litre shows on top of "Diesel Settings" as one
  clear value with a "Change price" button for users who may edit it (the value is still
  `Card Company Settings.diesel_unit_price`; a company picker appears only when the user has several
  companies; users who cannot read the price do not see the box). The main diesel section keeps only the
  supplier policy and the supplier. Transport prices per project move to "Transport Settings", cost centers
  per workshop to "Warehouse & Cost Centers", and the four role fields to "Advanced Permissions", shown only
  to users who may change them. No field, permission, validation or stored value changed; two field help
  texts were removed.
- **Apps screen (G4):** the Card entry is hidden from Website Users and from users who can read
  none of the CARD Desk documents (Card Equipment, Card Monthly Card, the supplier and customer
  registries, Equipment Transport, Project Diesel Fill, Equipment Needs Review, Employee Tool
  Custody) — operators, for example — as Frappe HR does; a second entry, *Card Mobile*, opens
  `/cdms` for users with a CARD portal role and an Active Employee. An operator who signs in at
  `/login` lands on Frappe's apps screen (`/apps`), where Card Mobile is offered and the Card Desk
  entry is not (verified on a dev site, Frappe 16.51.1).
- **Operator item search (G1):** `search_items` lists only enabled stock or purchase items (no
  templates), 20 at most, with code, name and unit only — the documented exception to the
  operator's lack of Item read permission.

### Fixed
- **CARD tests no longer rewrite the bench-wide translation files.** `test_mobile`'s Card Mobile translation test
  called Frappe's `compile_translations`, which writes `sites/assets/locale/ar/LC_MESSAGES/card.mo` for the whole
  bench, so a test run from any branch changed the Arabic translations every site of that bench shows (found on the
  QA bench on 2026-10-23). The test now compiles Card's Arabic catalogue in its own process, with Frappe's compile
  step, into a temporary folder and reads it from there; no `.mo` file of the bench is written. It still clears and
  refills the site's translation cache while it runs (also before this change), and clears it again at the end,
  also on error. Test-only change: no product, permission, data or API impact. Rollback: revert the commit.
- **Tool lines and tool custody: item type and company checks (issue #113, PR-T1; Owner decisions T3, T4,
  2026-10-23).** A tool goes into employee custody, so a Tool line of an Equipment Needs Review with an approved
  quantity must be a stock item and not a fixed asset; the review refuses it on save and `card.materials.approve_review`
  checks it again before it makes any Material Request (the Item can change after the review). Before, a non-stock
  Tool line reached a Material Request that ERPNext could never fulfil, and a fixed asset was refused only later by
  the custody record. Setting the approved quantity to 0 still refuses the line; Part lines are not changed. Employee
  Tool Custody now refuses a non-stock item on a Handover when it is saved (before, it failed only when its Stock
  Entry was made); other movements keep only the fixed-asset check, so a tool already held can still leave custody.
  Every linked record must belong to the employee's company: the receiving employee of a Transfer (before, a tool
  could be transferred to an employee of another company), the warehouse, the project, the equipment and, for
  movements that move stock, the custody store of Card Settings. Shared check `card.materials.tool_item_error`. Two
  new CARD strings with Arabic translations. Tests (`test_v4_materials`): `test_a_tool_line_must_be_a_stock_item`,
  `test_a_tool_line_cannot_be_a_fixed_asset`, `test_approval_checks_the_tool_item_again`,
  `test_custody_refuses_a_non_stock_item`, `test_custody_stays_in_the_employees_company` (they fail on main and pass
  with the change) and `test_a_held_tool_can_still_be_transferred_after_its_item_changed`. Impact: validation only;
  no permission, workflow, schema, accounting or API change; existing submitted records are not checked again (only
  a new save, an amend or a new movement). Rollback: revert the commit; no data to restore.
- **CARD Mobile: the Part / Tool choice of a request line is shown (PR #112).** `NewRequest.vue` passed the two
  kinds to frappe-ui `TabButtons` as `buttons`; frappe-ui 1.0.2 reads `options`, so the choice rendered empty and
  every line was sent as "Part" — an operator could not ask for a tool from CARD Mobile (since the first CARD Mobile
  commit, 683bfc4). The prop is now `options`. Tests: vitest (the page gives the kinds Part / Tool to `TabButtons` as
  `options`; the request sent to `card.materials.submit_needs` carries the chosen kind); `test_v4_materials`:
  `test_operator_asks_for_a_tool` (the server stores Tool / Part), `test_a_tool_stays_a_tool_through_review_and_approval`
  (the review keeps the kind; approval makes a Material Transfer to the tool custody store) and
  `test_a_tool_needs_the_custody_store_before_approval`. Browser check on a local build with test data (no ERPNext) at
  8 widths from 320 to 1440 px, English and Arabic. No server, permission, data or API change; tool lines from CARD
  Mobile now reach review, so approving them needs the tool custody store in Card Settings (Materials), as for tool
  lines from Desk or the older worker page. Lines sent from CARD Mobile before this fix stay "Part"; the fix does not
  change them. Rollback: revert the PR #112 commits; tool lines and draft Material Requests made after the fix stay.
- **The report row of the Card Materials sidebar now reaches upgraded sites (FR-077).** PR #108 added the
  "Equipment Make Model Values" row but kept the file's `modified` time. Frappe imports a standard Sidebar on
  `migrate` only when the file is newer than the stored document, so a site that already had the three FR-077 rows
  kept them and never got the fourth (found on the dev site after the merge; a fresh install was not affected).
  The file's `modified` time is now later, and `test_v3_navigation` now says "bump it" when stored rows differ from
  a file that is not newer than the stored sidebar. Impact: the next `migrate` replaces the shipped Card Materials
  sidebar (14 rows); site and user customizations are kept (they are stored in `Custom Sidebar`); no permission,
  data, accounting or API change. Rollback: reverting the commit does not remove the row from migrated sites (the
  older file time is never imported again); a later sidebar change must set `modified` after 2026-10-23 13:00.
- **Two assignments of one machine at the same time no longer overlap (D4, FR-075).** The overlap check of a
  Card Equipment Assignment was a plain read. Under MariaDB REPEATABLE READ (Production: MariaDB 10.6) two
  requests for the same machine that ran at the same time both saw "no overlap" and both saved: two new
  assignments, or a new assignment while a transport cancel reopened the previous one. The check now locks the
  machine's Card Equipment row first, so a second writer of that machine waits, and then reads the machine's
  assignments with a locking read, which returns the latest committed rows. The second request is refused with
  the normal overlap message. On a MariaDB server with `innodb_snapshot_isolation` ON (the 11.8 default) the
  refused request can end with a "record has changed" deadlock error instead; nothing of it is written. The
  `equipment` field of Card Equipment Assignment gets a database index (`search_index`), so the locking read
  locks that machine's rows and the index gap next to them, not the whole table; `bench migrate` adds it
  (`ADD INDEX equipment_index`), no patch. Run the migrate before the new code serves requests: without the
  index the locking read locks every assignment row. Affected: `CardEquipmentAssignment.validate_no_overlap`
  (manual saves, Equipment Transport submit and cancel). Not changed: what counts as an overlap, transfer dates,
  permissions, company rules, cards, billing and accounting. Residual (no overlap, nothing written): a save of an
  existing assignment locks that row before the machine row (Frappe `check_if_latest`), and a new assignment
  locks the machine row first, so the two at the same moment, or two transports of several machines in
  opposite order, can deadlock; the database rolls one back (HTTP 508, "try again"). Branch
  `fix/assignment-overlap-lock`, pull request not opened yet. Impact: permissions none, accounting none, data
  none (existing rows unchanged), API none, schema one index. SemVer impact: PATCH. (Target: next release.
  Rollback: revert; the index is harmless if kept, and a later release without `search_index` drops it.)
- **Diesel fill for Card User (P0):** a user with only the Card User role could not finish a Project Diesel Fill
  in the Desk. The Project, Cost Center and Supplier lists failed with "Insufficient Permission" (the role has no
  permission on those ERPNext masters), and the mandatory Supplier stayed empty and hidden when the user may not
  change it. The form now searches through `fill_link_query` (GET): only users who may create or edit a fill; the
  fill's company, which the user must be allowed to see; enabled leaf cost centers; the user's User Permissions;
  the Settings supplier only for users who may not change it; names and titles only. The form fills in the Settings
  supplier. The save refuses a project or cost center of another company, a group or disabled cost center, and a
  newly chosen disabled supplier, also through REST. No DocPerm, role or User Permission was changed. Impact:
  permissions — a fill user now sees the names and titles of the projects, leaf cost centers and suppliers the
  query allows, through the fill form only (the method checks fill rights and company itself); API: one new GET
  method, `fill_link_query`; accounting none; data none. (#84, merge `85ad66d`; FR-001, FR-038 (diesel fills
  only). Target: next release. Rollback: revert the merge; no schema, migration or data change. A code revert does
  not remove or change diesel fills already saved.)
- **Arabic: CARD no longer overrides the ERPNext translations of "Model" and "Unallocated".** CARD loads
  last, so a generic word in `card/locale/ar.po` replaces the Frappe/ERPNext translation on the whole site, against
  the rule that the CARD locale carries CARD strings only. ERPNext `version-16` now translates both words
  («الطراز», «غير مخصص»), and the guard `test_no_generic_msgid_overrides` failed in CI. The two CARD entries are
  removed; the test is unchanged. Visible change in Arabic: the Card Equipment field "Model" shows
  «الطراز» (was «الموديل») and the diesel consumption report row without equipment shows «غير مخصص» (was «غير مخصّص»).
  Impact: permissions, accounting, data and API none. SemVer impact: PATCH. (Target: next release. Rollback: revert;
  locale only, no schema, data or migration change.)
- **Arabic: CARD no longer overrides the Frappe translation of "Owner".** Frappe `version-16` now translates
  "Owner" as «مالك» (crowdin sync, merged 2026-10-22), and the CARD entry «المالك» replaced it on the whole site, so
  `test_no_generic_msgid_overrides` failed in CI. The CARD entry in `card/locale/ar.po` is removed; the test is
  unchanged. Visible change in Arabic: the Card Monthly Card field "Owner" (the supplier link) shows «مالك» (was
  «المالك»). Feature Registry not changed: no registry row covers the translation layer (same as the "Model" entry).
  Impact: permissions, accounting, data and API none. SemVer impact: PATCH. (Branch `fix/i18n-owner-msgid`. Target:
  next release. Rollback: revert; locale only, no schema, data or migration change.)

### Security
- **The equipment Asset picker follows the ERPNext Asset permissions (FR-079).** The Asset field of Card Equipment
  (and "Create from Asset") now lists Assets through `frappe.get_list`: only for a user who may create or edit
  equipment and read Assets, with the Asset User Permissions and the Asset company scope applied, as the save of
  the link already required. When an Asset is already linked, the other equipment is named only to a user who may
  read that Asset. `card.api.available_assets_query` declares `methods=["GET"]`. No role, DocPerm or setting
  change: a user without Asset read sees no Asset list (such a user could not save a link before either).
  Accounting, data and the API shape are unchanged. (#117) Rollback: revert the merge.
- **The equipment needs stock hint follows the user's stock rights (F2).** The supervisor's review stored
  the stock on hand on every line, read without any permission check, so every reader of the review
  (Card User included) saw stock quantities in the form, REST, report view, export and print, and the
  Equipment Needs Summary report showed them to every report role, summed over every company's
  warehouses. Stock is now read with the user's own ERPNext rights and shown only to a user whose roles
  read Bin and Warehouse (a shared Bin or an if_owner read does not count): only the warehouses he may
  read (Company and Warehouse User Permissions apply), limited to the review's company on the form and to
  the report's companies in the report. A warehouse he may not read gives no figure, never a false 0. The
  form shows the figure live (`card.materials.review_stock`, GET, needs read on the review); the report
  removes the column for a user without stock rights. The review line no longer stores it (`stock_qty`
  stays as an empty, print-hidden column); patch `v4_0_0.clear_review_stock_qty` clears the stored
  figures. Affected: `card/materials.py`, Equipment Needs Review (controller, form script), Equipment
  Needs Review Item (`print_hide`), Equipment Needs Summary. Permissions: none widened; a supervisor or manager without an
  ERPNext stock role no longer sees the hint. Accounting: none. Data: derived hint figures cleared; quantities,
  requests and Material Requests untouched; old review Versions keep the figures they recorded (kept as audit
  history, counted by the patch). API: new GET `card.materials.review_stock`. Rollback: revert the commit;
  the cleared hints are not restored (the next review save would store them again on the old code). FR-074.
- **Equipment assignments follow the user's company.** A Card Equipment Assignment has no Company field,
  so a Company User Permission never reached it: a user limited to one company could list, open and
  search the assignments of another company, and a Card Manager limited to one company could create and
  change them through the API. An assignment now belongs to its equipment's company for lists, link
  search, single reads and saves (`has_permission` + `permission_query_conditions`); a saved row can
  neither be changed by another company's user nor moved between companies. Unrestricted users,
  System Manager and Administrator are unchanged; transports still open and close assignments; no
  role gains a permission. (#85, merge `735d126`; FR-070. Target: next release. Rollback: revert the merge;
  no schema or data change.)
- **Monthly cards follow the user's company (D2).** Frappe checks the create and write permission on the
  values the client sends and only then fills a card's company from its equipment, so a user limited to
  company A who left the company empty could create a Card Monthly Card for company-B equipment, move an
  own draft card to company-B equipment, or take over a company-B draft card (Desk, REST, `set_value`).
  A `has_permission` hook now denies any card whose sent company or new equipment, or whose saved company,
  belongs to a company the user may not see (the Company User Permissions that apply to cards); it covers
  read, create, save, submit and cancel. Users without a Company User Permission (System Manager included)
  and Administrator are unchanged; no role gains a permission; no schema or data change. (#90,
  merge `9aa9184`; FR-071. Target: next release. Rollback: revert the merge; no schema or data change.)
- **Equipment transports follow the user's company (D3).** A transport checked that each machine belongs
  to its company, but not the project it goes to: a company-A transport could name a company-B project
  and take that project's cost center (submit was already refused by the assignment company check), and a
  user limited to company A could take over a company-B draft transport by sending company A (REST save,
  `set_value`). The transport's project (destination, or the project left on a return to the supplier)
  must now belong to the transport's company, for every user. A `has_permission` hook denies a transport
  whose sent or saved company (or, with no company sent, whose machines or project) belongs to a company
  the user may not see (the Company User Permissions that apply to transports); it covers read, create,
  save, submit and cancel. Transport costs, splits, prices, postings and transfers are unchanged; users
  without a Company User Permission and Administrator are unchanged; no role gains a permission; no schema
  or data change. (FR-072. Target: next release. Rollback: revert the commit; no schema or data change.)
- **Period lock: request keys that are not date fields are ignored (partial fix).** The lock looked for
  `to_date`, then `date`, then `posting_date` on the document as sent. Project Diesel Fill and Equipment
  Transport have no `to_date` field, but Frappe keeps any extra key of a request (`frappe.client.save` and
  `submit`, REST `PUT`, Desk save, submit and cancel), so a request with `"to_date": "2999-01-01"` could save,
  submit or cancel a fill or transport dated inside the locked period. A date key is now read only when it is a
  field of the DocType. This closes only the bypass through keys that are not real date fields; a cancel
  request that changes a real date field is a separate fix. Card Monthly Card (its `to_date` is computed from
  the month), the override role and the lock date are unchanged; no role gains a permission. (#97, commit
  `bec863a`, merge `2b7debf`; not released or deployed; FR-050. Target: next release after v4.0.0. Rollback: code only, revert
  the merge commit; no schema, data, fixture or migration change.)
- **Period lock: changing a document's date cannot get round the lock.** A save or submit was judged by
  the new date only, so a draft dated inside the locked period could be moved to an open date (or submitted
  with one) in the same request. On cancel Frappe skips `validate` and stores the values the request sent
  before `on_cancel` runs, so a Desk cancel request (`savedocs`, action Cancel) that changed a real date field
  (`to_date` of a Card Monthly Card, `date` of a Project Diesel Fill or Equipment Transport) could cancel a
  document of a locked period and leave the sent date on it. Now: a save or submit is refused when the date
  stored before the request or the new date is in the locked period; a cancel is judged by the stored date,
  and a cancel request that changes a period-lock date field is refused in every period (also for the
  override role), so a cancelled document keeps its original date. The override role still allows saving,
  submitting, moving and cancelling inside the locked period; normal work in open periods, delete and
  update after submit are unchanged (Frappe already refuses date changes after submit); no role gains a
  permission. Functions: `card/period_lock.py` `enforce`, `on_validate`, `on_cancel`; 1 new Arabic message.
  (#97, commits `3fbed47` and `c3d143a`, merge `2b7debf`; not released or deployed; FR-050. Target: next
  release after v4.0.0. Rollback: code only, revert the merge commit; no schema, data, fixture or migration change.)
- **Equipment transport rows are written through the transport only.** `POST`, `PUT` and `DELETE`
  `/api/resource/Equipment Transport Item` and `frappe.client.save` of a row saved one row alone (also
  when sent with docstatus 2, which Frappe treats as a cancel without any validation): Frappe
  checked only the transport's permission and skipped the transport's checks (company, movement,
  duplicates, cost shares, assignment links). A user limited to company A could so add a row with a
  company-B machine and its assignment to a submitted company-A transport, and cancelling the transport
  then deleted or reopened company B's assignment. A row written alone (insert, save, update after
  submit, delete) is now refused; the transport's own save, submit, cancel and delete and the REST calls
  that go through the transport (`frappe.client.insert`, `set_value`, `delete` of a row) are unchanged.
  Cancel now undoes only the assignments the transport itself wrote: of the row's machine, of the
  transport's company, on its project and date, and claimed by no other submitted transport. When a row
  links an assignment that was changed after the transport or never written by it, the cancel is refused
  with a message (the transport stays submitted), so a move is never half undone; an assignment deleted
  since has nothing to undo and is passed over. A cancel is also refused while a later move of the same
  machine relies on it, including a second move on the same date (it closed the assignment this transport
  opened, or opened its own); cancel the later move first. An assignment the transport opened and someone
  closed since counts as changed. The cancel reads the machine's transport rows and the assignments with
  a row lock, so it sees a move of the same machine submitted meanwhile (`card/transfer.py` `_depends_on`,
  `_written_by`). A cancel request that
  changes the transport's details or rows (a save with docstatus 2 stores what the request sent) is
  refused; the transport is cancelled as approved. No change to transport cost, cost bearer, split, price, cost center or
  postings; no role gains a permission; no schema or data change. (Branch
  `fix/transport-item-standalone-rows`, commits `771aa63` and the same-date cancel fix; not pushed, merged, released or deployed;
  FR-073. Target: next release. Rollback: revert the commit; no schema or data change.)

### Migration
- From v1.0.1 (the version on the first production site) the upgrade runs, once each, the patches of v1.2.0,
  v1.2.1, v1.2.2, v3.0.0, v4.0.0 and this release (21 patches; 24 CARD patches in total). Rehearsed on frappe
  16.51.1 / ERPNext 16.50.0 with synthetic v1.0.1 data shaped like a site in use (workflow
  `upgrade-rehearsal.yml`): every machine, assignment, monthly card, day row and amount unchanged; no GL, payment,
  stock, invoice, journal or Material Request document created; no transport created for past months; no user
  given a Card role; a second migrate changes nothing.
- New in this release: `v4_0_0.clear_review_stock_qty` (empties the stored stock hint of reviews made before the F2
  fix) and `v4_1_0.backfill_equipment_identity_keys` (comparable chassis / plate keys; numbers already shared are
  listed in the Error Log and kept).
- New DocTypes since v4.0.0: Card Equipment Make, Card Equipment Model, Card Equipment Part; new Desk page
  `tool-custody`; new columns on Card Equipment, Employee Tool Custody and the needs request / review items.
- Old code cannot run on the migrated data: rollback = restore the pre-upgrade backup (only while no new business
  record was entered), otherwise fix forward.
- After an upgrade from v3.0.0 or older: record the first transport of every working machine before its next
  monthly card (a monthly card needs an approved transport for the month); past cards stay as they are. Set the
  ERPNext cost center of every project that receives equipment.

### Known limitations
- CARD Mobile (`/cdms`) is built and served, but not yet tested on real phones; it is not part of the first
  production go-live (P1–P3).
- Fitment phase 2b (PR #110) is not in this release.
- Material Requests, Stock Entries and invoices made by CARD stay drafts; ERPNext users submit them.
- Published ≠ deployed: this release is not yet deployed to any production site.

## [4.0.0] — 2026-10-19

Equipment materials (Owner plan `2026-10-19_card-equipment-materials-phase1-plan.md`): the operator
named on a machine asks for its needs, the supervisor reviews and consolidates them, management
approves, and the approved lines become standard ERPNext Material Requests. Requires v3.0.0.

### Added
- **Operator page `/equipment-needs`** (mobile-friendly, the user's own Frappe account, no Desk needed):
  the operator picks one of his machines (named on the equipment or on its monthly card this month)
  and asks for parts/consumables or tools with quantity and reason; he sees his recent requests and
  their status. Server-rendered and translated by Frappe (English source; Arabic, Bengali, Hindi,
  Urdu). New role **Card Operator** — operators see only their own requests; the page sends the
  session's CSRF token with every request.
- **Equipment Needs Request**: one request per machine; project from the machine's approved
  transport; the operator, the person who entered it and "on behalf" are kept; an item asked again
  for the same machine within the Settings window (default 30 days) is flagged for review only.
- **Equipment Needs Review** (new role **Card Supervisor**): pulls the project's submitted requests;
  keeps the requested quantity unchanged and records the quantity found on site, the approved
  quantity, the site inspection (or "not inspected"), the supply route (from store / buy for the
  project) and the warehouse; stock on hand shown per line.
- **Management approval** (Card Manager): creates draft ERPNext Material Requests — Purchase (buy
  for the project), Material Issue (from store) or Material Transfer to the tool custody store
  (tools) — each row with item, project, cost center and the Card Equipment dimension (parts).
  ERPNext's own "Make Stock Entry" keeps the equipment and project, so the cost reaches the machine
  only when stock is issued to it. CARD writes no GL entry.
- **Employee Tool Custody**: handover, return, transfer between workers, loss and damage of
  returnable tools, with one shared custody store (no warehouse per worker); handover/return create
  a draft Material Transfer, loss/damage a draft Material Issue and a review flag — never a salary
  deduction or HR violation. Fixed-asset tools stay on the ERPNext Asset (custodian / Asset Movement).
- **Reports**: Equipment Needs Summary (the consolidated list for management, with each machine's
  share), Equipment Consumption (issues + non-stock purchase lines, each counted once), Worker
  Custody (returnable tools + assets with a custodian), Repeat Equipment Requests.
- **Launcher**: a "Card Materials" entry with its sidebar; Card Settings gets a Materials tab (main
  store, tool custody store, repeat window).

### Security
- Operators reach only their own machines and requests (record rules on Desk, REST and the page);
  supervisors limited by a project User Permission see only those projects, in documents and in
  the Equipment Needs Summary / Repeat Equipment Requests reports.
- The operator page gives the session its CSRF token, so every request it sends is CSRF-checked.
- Approval creates the Material Requests with the approver's own ERPNext rights (no permission
  bypass); approval fields and requested quantities cannot be written by hand or through REST;
  a second approval is refused under a row lock, so Material Requests are never duplicated.
- A custody cancel removes only the draft Stock Entry that movement created.

### Migration
- Patch `v4_0_0.ensure_materials_roles` creates Card Supervisor and Card Operator and sets Card
  Operator to no Desk access once. New DocTypes only; nothing existing is changed or deleted.
- Before use on a site: link worker Users to their Employee records, give operators the Card
  Operator role, set the two stores in Card Settings → Materials, and make sure the Card Equipment
  accounting dimension exists (without it the requests work but rows carry no equipment).
- CARD roles add to ERPNext's own permissions; they do not replace them. Approvers (Card Manager) also
  need the right to create Material Requests (for example Stock User or Purchase User): the requests
  are made with the approver's own ERPNext rights. Supervisors working in Desk need read access to
  projects, warehouses and employees (for example Projects User + Stock User). Card Supervisor gets
  read-only access to Card Equipment; limit it per company with standard User Permissions.
- An operator linked to an Employee also gets ERPNext's standard Employee role, which opens Desk; the
  operator still sees only his own requests and no equipment, stock or custody records.

### Known limitations
- Material Requests and Stock Entries are created as drafts; the buying/stock team submits them.
- The Equipment Consumption report needs `report` access on Card Equipment, which Card Supervisor
  does not have: supervisors get "not permitted" there (management, Card User and stock roles run it).
- Custody movements create their draft Stock Entry for the stock team without the creator's own
  stock rights (drafts only; submitting needs the stock role).
- The DAWM worker spare-parts flow is not used for equipment needs (Owner decision) and is not
  changed by CARD.

## [3.0.0] — 2026-10-19

Major release: a unified navigation (CARD launcher) and the first data-flow changes of the
"CARD Unified UX" design — transports drive where a machine is, the monthly card follows the
approved transports, and an owned machine takes its details from its ERPNext Asset. Built and
verified on **frappe 16.51.1 / ERPNext 16.50.0 / HRMS 16.51.0**, which have `Dock` and app-shipped
`Sidebar` documents. The oldest frappe version with both has not been determined (**Unknown**), so
check the frappe version of a site before upgrading it. The version number jumps from 1.2.2 to
3.0.0 by owner decision; no 2.x release exists.

### Added
- **CARD launcher.** The app ships a `Dock` with nine entries — Dashboard, Equipment, Movement &
  Transport, Operating Units, Operation Cards, Expenses, Suppliers & Customers, Reports, Settings —
  each opening its own sidebar of existing documents and reports. The Dashboard sidebar is reduced to
  the home page, monthly cards and transports.
- **One transport, several machines.** An Equipment Transport lists the equipment it moves in an
  equipment table. The trip cost is split equally across the equipment; any share can be edited, and
  the shares must add up to the trip cost. Submitting moves every listed machine to the project, and
  cancelling reverses each one. The monthly supplier posting carries one transport line per machine, so
  each machine gets its own share on the equipment dimension (the total is unchanged).
- **Simplified transport entry.** Pick the equipment ownership and supplier to narrow the equipment
  list (all of the supplier's machines, however old), then the **destination**: a project, a
  workshop, storage (an ERPNext `Location`) or back to the supplier (rented equipment only). Each
  machine's current place ("From") is read from its open assignment or its last approved move,
  filled in as soon as the machine is picked; a machine never assigned to a project starts from
  storage (its first move). A move to where the machine already is (same project or same place) is
  refused. Moving to a workshop, storage or the supplier ends the project assignment on the
  transport date: no new card days after it, earlier cards stay. From and To are never typed: From
  is the machine's current place, To is an ERPNext project or a registered place (the old free-text
  From/To are kept hidden for older documents). The cost is always charged to where the equipment
  goes: the destination project's cost center, or the workshop/storage place's cost center set per
  company in Card Settings; a return to the supplier stays on the project it leaves. **Transport
  cost borne by**: Company (billed by the transport supplier, as before), Equipment Supplier (no
  cost, no invoice) or Customer (recorded for follow-up, not invoiced yet). Only Company-borne moves
  reach the supplier posting and the transport/operating cost reports.
- **Monthly card follows the approved transports.** Pick the equipment, month and year; the project
  is the one the equipment's approved transports put it on that month (Card Equipment Assignment),
  filled in and locked. A machine that stays on a project keeps an open assignment, so it gets a card
  every month and per shift (day and night). Moved during the month: one card per project (same shift
  allowed once per project), and only that project's days are offered. No transport covering the
  month: the card is refused with the reason. A project outside the assignments is refused, also
  through the API. Company operators are picked from Employee; a rented machine's operator is typed.
  The card's rate is unchanged (dated rate agreements are planned for a later release).
- **Equipment from its ERPNext Asset.** The Asset field sits next to ownership (owned and
  managed equipment); picking it fills the name, image, cost center, custodian as operator and the
  insurance details, keeping anything already typed. Owned equipment defaults to company operator
  and fuel. The Documents tab comes second and the form warns about documents that expired or
  expire within 30 days.
- **The Asset owns the equipment details.** With an Asset linked, the equipment name, brand
  (from the Asset item) and type (from the new *Asset category* on the equipment type, one
  category per type) come from the Asset and are read-only; brand, model, year, chassis and plate
  are hidden when empty. The values are re-applied on every save. A one-time patch
  (`sync_equipment_from_asset`) aligns equipment linked before this release.
- **Company filled automatically** on new equipment, transport and diesel forms when the user can
  see only one company; the field stays visible and editable.
- **Dated unit components.** A unit is still one equipment on its monthly card (billing unchanged).
  Each component now has From/To dates, and the unit form offers **Replace component** and **Move to
  another unit**. Both are refused inside an approved card period, and a piece must be on the unit's
  project. Card-day checks count a component only between its dates. Changing components needs
  write access to them (Card Manager); Card User does not get the actions.
- **Expenses sidebar** links the standard documents that carry equipment costs (Purchase Invoice,
  Asset Repair) next to diesel and transport. No CARD expense document is introduced.

### Changed
- The Equipment Transport header `equipment` is now derived from the first row of the equipment table
  and hidden; a patch gives every existing transport its single row (amount, assignments) unchanged.
  Each machine's Connections tab lists every trip it was on, and the transport print lists every
  machine with its share.

### Fixed
- **Unit component integrity on concurrent and direct-row writes** (#59): changing a
  component through the raw child-row endpoint (`PUT /api/resource/Card Equipment
  Component/<row>`, `frappe.client.save`) is refused with a pointer to edit the unit itself,
  whose save is serialized and recorded in its Version history (direct row updates left no
  Version entry); validation now takes locking reads (`for_update`) on the component's
  equipment row and on the membership rows, so two saves claiming the same component run one
  after the other against committed data (a crossed lock order can abort one save, never
  admit both). Role-only row edits still save. No schema or data change.

### Security
- An Equipment Transport now drops assignment links sent with its submit (they were cleared only
  for drafts); cancelling a transport only deletes or reopens assignments of its own machines. Found
  by the release security review in unreleased v3 code; no published version is affected.

### Template library
- Add a document-design library under `docs/templates/` and archive the monthly equipment
  operating card D0.6 (Arabic/English, landscape front, portrait reverse, 31 days, overtime,
  signatures and totals) with editable HTML/CSS sources, field mapping, font license and
  validation evidence. Proprietary SDCE assets (logo, branded PDF and previews) are not
  distributed, and the public template ships with a neutral placeholder identity
  (`company-logo.png`, «اسم المؤسسة / COMPANY NAME», `FORM-CODE`). Documents the required
  home for future printable designs — design assets never ship inside the installable `card/`
  package. No runtime Print Format, schema or deployment change.

### Breaking changes
- **A monthly card needs an approved transport.** The card's project comes only from the
  equipment's assignments in that month. Equipment with no assignment covering the month cannot
  save a card (new or re-saved draft) until an Equipment Transport records its move. Sites whose
  equipment never used transports/assignments must record them before the first v3 month closes.
- A card's project outside the equipment's assignments is refused, also through the API.
- With an ERPNext Asset linked, the equipment name, brand and (when mapped) type follow the Asset on
  every save and are read-only.
- A transport to the project the machine is already on is refused; From/To are no longer typed.

### Migration
- `bench migrate` runs two new post-model-sync patches, once each, idempotent:
  - `v3_0_0.backfill_transport_items` — gives every existing transport its single equipment row
    (amount and assignment links unchanged). Writes no GL entry, invoice or card amount.
  - `v3_0_0.sync_equipment_from_asset` — sets the name, brand and mapped type of every equipment
    linked to an Asset from that Asset (direct writes; documents that copied the old name keep it).
- New DocTypes: `Equipment Transport Item` (child), `Card Location Cost Center` (child of Card
  Settings). New fields on Equipment Transport, Card Monthly Card, Card Equipment Component and Card
  Equipment Type (`asset_category`). Nothing is deleted.
- After upgrading: set the workshop/storage cost centers in Card Settings, map Asset categories to
  equipment types, and make sure every working machine has an approved transport for the month.
- Rollback: no down-migrations; restore the pre-upgrade backup.

### Known limitations
- Requires the frappe Dock/Sidebar navigation: verified on 16.51.1 only; earlier 16.5x minors are
  **Unknown**; pre-16.50 sites stay on v1.0.1.
- ERPNext's Asset has no model, year, chassis or plate fields: on equipment linked to an Asset these
  are hidden unless already stored.
- Customer-borne transport is recorded for follow-up only, not invoiced.
- Dock entry tooltips stay in English (frappe core).
- Older CARD forms outside transport and equipment still show some field help texts.
- Published ≠ deployed: this version is not deployed to any production site.

## [1.2.2] — 2026-10-17

Patch release on top of 1.2.1: company isolation of the registries and the posting endpoints,
protected commercial terms and equipment fields, a permanent GL Posting Log, and posting, diesel,
report and reconciliation fixes. Merged through PRs #30, #39, #55, #58, #60 and #65; CI and test
maintenance in PRs #63, #66 and #67.

### Security
- **Monthly-posting endpoints are company-scoped** (#36). `post_month` / `rebuild_month` refuse,
  before any work, a company outside the caller's permitted companies (User Permission rule of the
  reports). On QA the case was already blocked late, and incidentally, by ERPNext's party-account
  permission check; the gate is now explicit.
- **Supplier/customer registries no longer expose other companies** (#23). Registry rows store no
  figures any more (the stored party-wide counts, hours and totals are cleared by a patch); the form
  shows figures per company the user may see. A user restricted to some companies lists and opens only
  parties with cards there (list, form and REST). The registries' earlier change history, which holds
  those figures, is **kept unchanged as audit history** and is not shown: the registries do not track
  changes (turning it on through Customize Form or a Property Setter is refused), and Version records
  are readable by System Manager only. A patch only counts that history; nothing is deleted.
- **The Monthly Card keeps its current default print format.** On upgrade, an existing print-format
  default (e.g. the legacy «كارت تشغيل شهري») is kept; the new "Card Monthly Card Print" stays
  available in the print menu, and new installs use it as the default.
- **Commercial terms of equipment are protected** (rates, rate basis, daily hours, direction, parties,
  contract, fuel): permission level 1 (Card Manager writes, Card User reads), a new reason is required
  for every change, and the change history is kept. Card User no longer creates equipment.
- **Equipment assignments** are written by Card Manager only and validated (dates, company, no overlap);
  transfers record their assignment changes in the history.
- **Card Settings**: Accounts Manager can now save the per-company accounting fields (the previous
  level-1 grant could not be used); policy fields moved to permission level 2 (System Manager writes).
- Change history on Project Diesel Fill and Equipment Transport.
- **Equipment fields that drive company, accounting and the assignment control are protected** (#56):
  company, the linked Asset, unit / components / unit-component and the diesel consumption baselines
  are written by Card Manager only (Card User reads them). Server-side checks:
  - the company cannot change once the equipment is used;
  - a linked Asset must be of the same company, not cancelled, and readable by the user;
  - components must be of the same company, not units and not in another unit, also when a
    component row is saved on its own (REST on the row).
- **Current project and assignment date are read-only.** They follow the assignment in force today
  (project and start date) and are re-synced whenever an assignment changes or a transfer is
  submitted or cancelled; an overwritten value leaves a comment. A future assignment does not move
  them; a transfer that ends a previous assignment takes effect the day after its date (a first
  assignment starts on the transfer date). The free-text location is never changed.
  Moves that only come into force with time (a future start, an end date passing) are applied by an
  optional daily job, **off by default** (Card Settings); without it they wait for the next
  assignment event.
- **A unit's card days are checked against the unit's own assignments too.** A component without
  assignment history no longer switches the check off.
- **The GL Posting Log is a permanent audit record** (#57): no role can create, edit, delete or share
  a log (System Manager keeps read, report and export), and the server refuses these operations even
  for Administrator, shared documents or a Custom DocPerm. Only CARD's monthly posting creates a log, for
  its own draft invoice; the lifecycle (submit, cancel, draft deletion, rebuild) is unchanged. Cancelled
  and stale logs are kept, so a cancelled Card invoice can no longer become amendable by deleting or
  rebinding its log. The source rows cannot be changed on their own. Delete Company Transactions and
  app uninstall keep working.

### Fixed
- **Project names in reports for operational roles** (#29, PR #30).
- **Diesel reports mark estimates** (#33): litres split from project-tank fills by operating hours are
  shown as *estimated*, direct fills as *recorded*; "Actual litres" is now "Allocated litres".
- **Monthly posting lines** (#34): fill/transport lines use the source's own cost center when set;
  split diesel lines state their own estimated litres share.
- **Reconciliation in three separate figures** (statements and summaries, net before VAT): **invoiced
  through Card** (from Card's own posting trail), **not invoiced through Card** (card net − invoiced through
  Card; cards in a Card draft invoice count here until it is submitted; under a project or equipment-type
  filter only the shown cards' share of a Card invoice counts) and **ERPNext invoices outside
  Card — to reconcile** (submitted invoices of the party in the period that Card did not create). Invoices
  outside Card are shown for manual reconciliation only: never matched to cards by party and month, and no
  existing invoice, GL entry or amount is relinked or changed. GL figures stay as the VAT-inclusive balance.
  A manual invoice that takes the number of a deleted Card draft (frappe reuses the last number) is still
  counted outside Card: only a **submitted** Card posting makes an invoice Card's.
- **Clear message when a poster cannot read Items.** Building a monthly invoice needs Item read access
  (ERPNext prices the lines with the caller's rights); a Card Manager without it (e.g. Accounts Manager
  only) is now refused up front with a message naming the needed role, instead of an empty permission
  error from inside ERPNext. No rights are granted automatically.
- **Manual invoices that reuse a deleted Card draft's number can be amended again.** frappe reuses the
  last number after a draft is deleted, and Card refused every amendment of such a manual invoice. An
  amendment is now refused only when a Card posting record was written at or after the amended invoice
  (Card creates its invoice and that record together), and the whole amendment chain is checked: amending
  a cancelled Card posting — directly or through an earlier amendment — is still refused. Equal or
  missing timestamps refuse.

### Migration
- Upgrading from 1.0.1 runs the `v1_2`, `v1_2_1` and `v1_2_2` patches once each (all post-model-sync,
  idempotent). None writes GL entries, invoices or card amounts. On existing cards:
  - **submitted cards** get their snapshot fields (`daily_hours_used`, `hourly_rate_used`,
    `diesel_policy_used`) from the card's rate and the equipment's **current** daily hours and fuel
    policy;
  - an empty card direction is derived, and adjustment rows get `side = Supplier`;
  - draft cards are re-derived from their equipment.
- The supplier/customer registries are created or recomputed, and their stored figures are cleared
  (#23). Their earlier change history is only counted: nothing is deleted. An existing default print
  format is kept.
- The roles **Card Manager** and **Card User** are created; assign them to the users who operate Card.
- Accounting stays off (`enable_accounting = 0`), the `card_equipment` Accounting Dimension is not
  created (separate manual step), and the daily location sync is off.
- Rehearse the upgrade on a copy of production before deploying it.

### Known limitations
- The diesel *cost* totals (Equipment Diesel Consumption, monthly card form) still add recorded and
  estimated amounts into one figure; only the litres are split (#33).
- Rebuilding a monthly posting deletes CARD's draft invoice and creates a new one, which may take the
  same number; edits made on the deleted draft are lost. Affects only sites with accounting enabled.

## [1.2.1] — 2026-10-16

Patch release on top of 1.2.0: operational roles can run filtered reports, monthly-card and
diesel/transport prints show the right money on the right side, and supplier/customer totals keep
each side's own additions and deductions. Merged through PRs #22, #26 and #27.

### Fixed
- **Filtered reports for operational roles** (#21, PR #22). A Card User could not run any CARD
  report filtered by supplier, customer or project: Frappe v16 validates report Link-filter values
  against the user's own read/select permission. Supplier and customer filters now link to the CARD
  registries (*Card Equipment Supplier* / *Customer*), Company and Project are CARD-scoped
  Autocomplete filters, and master Link columns the user cannot read are returned as plain text — no
  ERPNext permission is granted to any Card role. The registries follow ERPNext Supplier/Customer
  renames and merges, and a row now exists from a party's first draft card (backfilled on migrate).
- **Monthly card print** (#25, PR #26). Each billed side prints the figures of its invoice — gross,
  that side's additions, deductions, and the net before VAT (supplier: `amount → net_amount`;
  customer: `customer_amount → customer_net_amount`); sub-rental cards print both sides and name the
  customer. A rented-out card with a 1,200 customer deduction printed "net due 0.00"; it now prints
  6,000. The supplier "total" box printed the net under a gross label; it now prints the gross. The
  Arabic overlap of mixed bold/regular text on the adjustments line is gone. The legacy alternative
  format prints the customer amount on customer-only cards.
- **Diesel fill and transport prints** (#25, PR #26). The money field is labelled "Fill amount"
  («قيمة التعبئة») / "Transport cost" («تكلفة النقل») instead of "Amount", which core Arabic
  translates as a quantity («كمية»); the two report columns read "Diesel cost" / "Transport cost".
  The amount in words is labelled «المبلغ كتابةً» and, in Arabic, shows the currency symbol (ر.س)
  instead of the ISO code. No core translation is overridden.
- **Supplier and customer totals keep each side's adjustments** (#24, PR #27). The supplier
  registry, *Equipment Suppliers Summary* and *Equipment Supplier Statement* no longer fold
  customer-side rows of sub-rental cards into the supplier net; the customer registry, *Equipment
  Customers Summary* and *Equipment Customer Statement* now use the customer net (what the Sales
  Invoice bills) instead of the gross, and the customer statement gains Additions / Deductions / Net
  columns. The card form's displayed net counts supplier-side rows only.

### Migration
- `bench --site <site> migrate` runs three idempotent v1.2.1 patches, in order:
  `backfill_customer_net_amount` (fills `customer_net_amount` on customer-billing cards saved before
  that column was computed), `ensure_party_registries` (creates missing registry rows and realigns rows an earlier party
  rename left misnamed),
  `recompute_party_registries` (refreshes every stored registry total). They write only that derived
  card column and the CARD registry rows; no submitted accounting document (invoice, journal, GL
  entry) is touched. A party whose recompute fails is logged in Error Log and counted in the
  migrate output.
- New Arabic strings: compile translations (`bench build`, or
  `bench compile-po-to-mo --app card --force`) and `bench --site <site> clear-cache`, otherwise the
  new labels show in English.

### Compatibility
- Frappe / ERPNext v16 (16.5x), as 1.2.0. No field is removed or renamed; only the labels of
  `amount` on Project Diesel Fill / Equipment Transport change. The default monthly-card print format
  stays "Card Monthly Card Print"; an existing site-level default is not overwritten.
- The internal whitelisted Link-query endpoints `card.api.card_projects_query` and
  `card.api.card_companies_query` are replaced by `card.api.card_project_options` /
  `card.api.card_company_options` (Autocomplete contract). A custom client calling the old names
  must switch.

### Test evidence
- CI green on every merged head (unit tests on Frappe 16.5x, pre-commit, Semgrep, CodeQL).
- QA v16 bench, full suite on each final head: PR #22 259/259, PR #26 260/260, PR #27 268/268;
  integrated main + all three: 280/280.
- Real PDFs rendered with wkhtmltopdf 0.12.6 (Arabic, fictional data): customer-only card (6,000),
  supplier card with additions/deductions over 31 days, sub-rental with mixed sides
  (16,200→15,900 / 24,300→24,150), diesel fill, transport — all single page, no overlap.
- Independent review of every PR, findings resolved before merge.

### Known limitations
- **Multi-company registry isolation is not resolved (#23, open).** *Card Equipment Supplier* /
  *Customer* rows and their stored totals are per party across all companies. Reports and their
  filters are company-scoped, but the registry totals are not — do not rely on them on a
  multi-company site until #23 ships.
- The reconciliation difference compares card nets **before VAT** with party GL totals that include
  VAT, so it does not reach zero for VAT-registered parties (pre-existing; owner decision pending).
- The legacy alternative print format «كارت تشغيل شهري» keeps pre-existing wkhtmltopdf layout
  defects (overlapping header text); use the default "Card Monthly Card Print".
- Amount in words uses the company's default currency (single-currency sites).

> Published ≠ deployed: this release is not deployed to any production site.

## [1.2.0] — 2026-10-16

First release since v1.0.1. The v1.1 line was developed and merged but **never tagged**; its
content ships here. Merged through PRs #1–#5, #12, #14, #16 and #18.

### Added
- **English-source UI with a complete Arabic translation** (v1.1 line). The app/module name
  "Card" is never translated; `card/locale` carries CARD strings only (guard test).
- **Desk connections** between equipment, cards, suppliers, customers and projects; workspace and
  sidebar polish; per-shift hour heatmaps.
- **Card Settings** (single) with one **Card Company Settings** row per company; **Card Manager** /
  **Card User** roles; permission levels (accounting fields at level 1 for Accounts Manager).
- **Rental directions on the equipment** (rented-in, rented-out, sub-rental, owned) with hours-only
  monthly cards; **customer registry**, *Equipment Customer Statement* and *Equipment Customers
  Summary* on official receivables.
- **Three rate bases** (hourly, daily, monthly) — all bill operating hours (see README).
- **Diesel and transport:** *Project Diesel Fill* with project-tank allocation by operating hours
  (one shared rounding rule for display and posting), unallocated fills reported explicitly;
  *Equipment Transport* with per-project prices; diesel supplier policy; reports *Equipment Diesel
  Analysis*, *Equipment Diesel Consumption*, *Operating Cost by Project*, *Transport Cost by Project*.
- **Card Equipment accounting dimension** (manual one-time setup step, documented in the module),
  guard report *Equipment Expenses Without Equipment*, period lock, equipment transfers with
  assignment tracking, professional RTL print formats (monthly card, diesel fill, transport).
- **Monthly supplier/customer postings (opt-in per company):** draft Purchase/Sales Invoices built
  from submitted CARD documents — one line per source document with project, cost center and
  equipment dimension — tracked by **GL Posting Log** units with fail-closed preflights (settings,
  items, tax template shape, dimension, open period) and lifecycle guards (active-unit resolution,
  submit-time re-assertion of period, month anchor and source totals, type-free reservation keys,
  multi-rate tax templates refused). Documents are always created as drafts for accountant review.

### Fixed
- **Report access** (#13 / PR #14): all nine CARD reports now run for one validated company; card
  and GL reads are scoped to it; ledger figures are shown only to users whose roles read GL Entry
  (a shared document or an owner-only read does not count); link filters use CARD-owned queries, so
  no ERPNext permission grant is needed to filter by company, project, supplier or customer.
  Previously an operational user could see ledger balances, and a multi-company site mixed companies.
- **Diesel allocation** now requires a company and scopes both fills and hour weights to it — a
  project spanning companies no longer mixes them in reports or in posting lines (PR #14).
- **Workspace number cards** no longer pin SAR: counts and litres were rendered as SAR amounts and
  non-SAR companies saw SAR (#15 / PR #16).
- **Arabic labels** for GL Posting Log fields (#17 / PR #18).

### Changed
- Report filters: **Company is required** (defaults to the user's company). *Equipment Expenses
  Without Equipment* is limited to System Manager and Accounts Manager.
- Repository presentation, CI (clean-site tests, linters, CodeQL, Semgrep) and copyright headers.

### Upgrade notes (from v1.0.1)
- Tested on **Frappe/ERPNext v16.50+** (earlier v16 minors are not tested for this release). Back up,
  then `bench --site <site> migrate`.
- Patches run once: `ensure_card_roles`, `backfill_snapshot`, `init_card_settings_defaults`,
  `set_operator_fuel_defaults`, `init_shift_limits`, `backfill_card_direction`,
  `backfill_rental_direction`, `rederive_draft_cards`, `backfill_adjustment_side`,
  `ensure_print_defaults`, `recompute_posting_keys`.
- **Accounting stays off** after upgrade: no posting happens until accounting is enabled and a
  company row is configured in Card Settings. Assign **Card Manager / Card User** to operational users.
- Users who should see ledger columns in CARD reports need a role that reads GL Entry
  (e.g. Accounts User / Accounts Manager).
- Before upgrading a multi-company site, list projects whose cards or diesel fills span companies;
  their diesel allocation is now per company.

### Compatibility
- Frappe 16.51.1 / ERPNext 16.50.0 (clean-site CI on 16.5x); `required_apps = ["erpnext"]`.

### Test evidence
- 246 app tests green on a Frappe 16.51.1 bench; clean-site install + full suite in CI; independent
  security/accounting review of the report-access change (two rounds, approved).

### Known limitations
- **Not deployed to any production site by this release.** A rehearsal of v1.0.1 → v1.2.0 on a
  copy of production data is required before a production upgrade.
- The broader accounting phases (per-company activation workflow, tax classes, claims, allocation
  shares) are an approved design and are **not** in this release.
- Some Arabic labels come from Frappe/ERPNext core translations (e.g. the list "ID" column, "Amount",
  "Total"); they can be adjusted per site with Translation records.

## [1.0.1] — 2026-10-13
Hotfix for Frappe **16.51** compatibility (the production framework upgrade to frappe 16.51.1 /
erpnext 16.50.0 / hrms 16.50.0 exposed a fixture that older Frappe accepted). No functional change
to the monthly‑card workflow.

### Fixed
- **Workspace fixture `module`:** `card/fixtures/workspace.json` shipped the *Card* Workspace with an
  empty `module`. Frappe ≥16.51 makes `Workspace.module` mandatory, so `bench migrate` failed in
  `sync_fixtures` with `MandatoryError [Workspace, Card]: module`. The fixture now carries
  `module: "Card"`, and the 5 `Card Monthly Card *-in_list_view` Property Setters carry
  `module: "Card"` (were empty).
- **Legacy `Card (Custom)` Module Def:** the installer now retires the orphan Module Def left by the
  original in‑site customization — idempotently reassigns any doc still scoped to it to the canonical
  `Card` module, then deletes the Module Def only if nothing references it (otherwise logs and keeps
  it; never force‑deletes). Runs on both install and migrate via the shared `_reconcile()`.
- **frappe 16.50 `Sidebar` fold:** 16.50 added the `Sidebar` doctype and its `convert_sidebars` patch
  (running before this app's patch, while the module was still `Card (Custom)`) rebuilt the Card
  navigation as a `Sidebar` named/moduled `Card (Custom)`. Because the desk resolves a module's
  sidebar by `{name==module, module==module}` (frappe `sidebar.py` `get_module_shell`), the installer
  now folds that record into the canonical `Sidebar` **name `Card` / module `Card`** — renaming it
  (keeping all items, header icon and `merged_from`) when no `Card` sidebar exists, or appending only
  the missing items then deleting the legacy one (never deleting a sidebar whose items are not all
  present canonically). Guarded for pre‑16.50 sites (no `Sidebar` doctype). Validate‑free
  (`frappe.rename_doc` + DB‑level item ops), so frappe's app‑owned/developer‑mode `Sidebar.validate`
  guard is never tripped during migrate. Delivered via a **new** patch
  `card.patches.v1_0_1.fold_sidebar_and_retire_legacy_module` (the v1.0 reconcile patch is already in
  the Patch Log of installed sites, and there is no `after_migrate` hook, so a fresh entry is required
  to reach already‑installed sites on upgrade). The fold is **cosmetic (desk navigation) and never
  aborts `bench migrate`**: the patch runs it inside a DB savepoint and, on any error, rolls back to
  the savepoint, logs to Error Log, and returns normally — the Workspace `module` fix (fixture) and
  the `net_amount` backfill (separate patch) are independent and unaffected. All frappe APIs used are
  pinned to the real v16.51.1 signatures (the rename uses `frappe.model.rename_doc.rename_doc(…,
  validate=False)`, which does the rename mechanics without `before_rename`/`validate_rename` and
  never calls `Sidebar.validate`).
- **`net_amount` backfill:** cards submitted before v1.0 (under the legacy Server Script) kept
  `net_amount` at 0/NULL while `amount` was non‑zero. An idempotent patch sets
  `net_amount = amount + total_additions − total_deductions` for submitted rows (field‑only
  `db_set`, no re‑submit, no GL impact); genuinely‑zero cards are left untouched. New cards already
  compute `net_amount` on validate.

### Added
- Test `card/tests/test_fixtures.py`: asserts every fixture doc with a `module` key names a non‑empty
  Module Def owned by app `card` (prevents a recurrence of the empty‑module incident), and that the
  legacy‑module retirement is idempotent.
- Tests for the `net_amount` backfill (restores net; idempotent; owned/zero cards untouched).

### Changed
- Packaged `__version__` aligned to **`1.0.1`** (was `0.0.1`). This resolves the v1.0.0 known
  limitation; the About dialog now shows `Card card: 1.0.1`.

### Compatibility
- Frappe/ERPNext **v16** including **16.51.1 / 16.50.0** (validated on 16.33.0, 16.36.1, and the
  16.51 production upgrade). v1.0.1 is required for Frappe ≥16.51.

## [1.0.0] — 2026-10-13
First official release as a standalone Frappe v16 app, at **exact production parity** with the
pre‑existing production‑native CARD setup (equipment DocTypes + monthly‑card workflow + two script
reports + Card workspace), converted from client/server scripts into an app with controllers,
reports, fixtures, and an idempotent installer.

### Added
- 8 DocTypes under module *Card* (Card Equipment, Card Equipment Assignment, Card Equipment Category,
  Card Equipment Type, Card Equipment Supplier, Card Monthly Card, + child tables Card Monthly Card
  Adjustment and Card Monthly Card Day).
- Script reports *Equipment Suppliers Summary* and *Equipment Supplier Statement* with supplier GL
  reconciliation (accrual credits / payment debits, opening/closing, matching difference).
- *Card* workspace (number cards, dashboard chart, shortcuts) and a single app‑owned desktop icon
  with the Card logo; the Arabic monthly print format `كارت تشغيل شهري`.
- Idempotent installer: adopts a pre‑existing custom Module Def "Card" (never deletes it), flips the
  8 DocTypes to `custom=0 / module=Card`, creates the `default_print_format` Property Setter,
  disables (never deletes) the legacy server/client scripts, ensures exactly one desktop icon, and
  appends the Card launcher to each entitled user's desktop layout (append‑only).
- Report controllers derive the company prefix dynamically from the global default company (no
  hard‑coded company name).

### Compatibility
- Frappe/ERPNext **v16** (validated on 16.33.0 and 16.36.1); `required_apps = ["erpnext"]`; no
  dependency on any other custom app.

### Known limitations
- The packaged `__version__` is `0.0.1` (bench scaffold default) while this release is tagged
  `v1.0.0`; they differ intentionally for v1.0.0 and will be reconciled to `1.1.0` next release.

### Deployment notes
- Installs on a legacy site with `install-app card --force` (adopts the existing Module Def).
- When baked into a Docker image whose runtime `sites/assets` is a volume symlink, card's static
  files must be materialized into the image's bench‑root `assets/card` (see README → *Baked into a
  Docker image*).
