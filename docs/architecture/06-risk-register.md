# Risk register

Scope: #54 asks for a reviewed risk register before coding. This is the register as read from the code at `main` @
`2210d91`. It lists risks that exist in the repository today, not hypothetical ones. Each row states the evidence, the
control that already exists, the residual risk, and the next action with its issue. Likelihood and impact use
Low / Medium / High, judged from the code, not measured.

A "next action" is a proposal for the owner; none is approved or started by this document. Anything that changes
behaviour for existing data must be opt-in per company or warn-only by default (policy).

## 1. Migration and release

| ID | Risk | Evidence | Existing control | Residual (L / I) | Next action |
|---|---|---|---|---|---|
| R-01 | A patch changes or clears data that a code revert does not restore | 27 patches in `card/patches.txt`. Data-writing ones include `v1_0.backfill_net_amount`, `v1_2.backfill_*`, `v1_2.recompute_posting_keys`, `v1_2.rederive_draft_cards`, `v1_2_2.clear_registry_aggregates`, `v4_0_0.clear_review_stock_qty`, `v4_1_0.backfill_equipment_identity_keys`, `v4_7_0.seed_diesel_price_schedule` | Each patch is documented as idempotent and field-only (no re-submit, no GL); the upgrade rehearsal migrates v1.0.1 to the candidate on synthetic data and migrates twice (`.github/workflows/upgrade-rehearsal.yml`, #119, #130); policy requires a verified backup and a written rollback plan before any production migrate | Low / High | Keep "restore from backup" as the only rollback for a migrated site and say so in each release note. Rehearsal on a copy of real volume stays an explicit owner step (#119) |
| R-02 | The Card Equipment accounting dimension is a manual step that alters about 53 tables | `card/dimension.py` docstring; `gl/preflight.require_equipment_dimension` | Build is fail-closed without it; never run by migrate or patches | Medium / Medium | Record the dimension step in the deployment checklist of every release that needs posting (#119) |
| R-03 | Documentation, registry and code drift | Registry and CHANGELOG are hand-maintained; this pack is too | `FEATURE-REGISTRY.md` rule: status needs evidence; reviews | Medium / Low | Update the matching architecture file in every PR that changes a state, hook or posting rule |
| R-04 | The v1.0.1 to current path is rehearsed with synthetic data on pinned frappe 16.55.2 and erpnext 16.54.0 only | `.github/helper/upgrade_rehearsal.sh` | Pins match the recorded production platform | Low / Medium | Re-pin when production upgrades; rehearse any frappe or erpnext minor change first |

## 2. Accounting integrity

| ID | Risk | Evidence | Existing control | Residual (L / I) | Next action |
|---|---|---|---|---|---|
| R-05 | The same operation is invoiced twice (by CARD and by hand) | Manual supplier invoices and accrual Journal Entries exist for older months | One active posting per party-month-side via a unique key; sources reserved and locked during a build; accountant must review hand-booked invoices of the month before a supplier build (`gl/integrity.manual_invoice_candidates`, `require_reviewed`); accrual and invoice linking (`journal_link.py`, `integrity.link_supplier_invoice`); `check_not_a_copy` at submit | Medium / High | The review of hand-booked invoices is a human judgement. Keep the reports `unbilled_card_work`, `diesel_invoice_reconciliation` and `card_settlement_status` in the month-end routine (#126) |
| R-06 | `ignore_permissions=True` appears in production code | 34 lines with `ignore_permissions=True` outside tests and patches, in `gl/posting.py`, `gl/masters.py`, `gl/integrity.py`, `gl/journal_link.py`, `transfer.py`, `api.py`, `party_registry.py`, `dimension.py`, `employee_tool_custody.py`, `install.py`, `notifications.py`, `tool_custody.py` | Each is behind a role and company gate (for postings: `gl/posting._checked_endpoint_args`; for the custody Stock Entry draft: the confirmer's own Stock Entry rights). `AGENTS.md` forbids using it to make something work | Medium / High | A new endpoint that skips the gate would be a privilege bug. Add a test that fails when a new `ignore_permissions` appears without an allow-list entry (#54 acceptance: permissions) |
| R-07 | VAT input assumed from a tax identifier on the supplier; customer sales always taxed | `gl/posting.py`, `gl/events.py` | Missing templates refuse the build instead of dropping VAT; multi-rate templates refused | Medium / High outside KSA | Move the two assumptions behind a company setting before a second country is onboarded (#54; see [04-localization-matrix.md](04-localization-matrix.md)) |
| R-08 | Customer-side non-taxable deduction and customer transport billing are not supported | `gl/posting.py` `_card_lines` raises; `record_financial_decision` records only | Refusal with a message; no silent posting | Low / Medium | Owner decision on the representation (credit note vs other), then build (#49, #41) |
| R-09 | Rates are not effective-dated | `Card Equipment` rate fields; CHANGELOG "Dated rate agreements" postponed (FR-023) | Submitted cards snapshot the rate used | Medium / Medium | A rate change reprices every later draft card. Keep the reason requirement; plan dated agreements (#41) |
| R-10 | Billing basis "per day" is hours-prorated, not full-day | CHANGELOG [Unreleased] "Planned": `amount = total_working_hours x (rate / daily_hours)` | Behaviour documented; unchanged | Medium / Medium | Owner confirms the default and the switch (FR-024) |
| R-11 | Reconciliation tolerance 0.01 is a site setting with `or 0.01` fallbacks | `settings.py`, `gl/*.py` | Same value everywhere; a setting of 0 falls back to 0.01 | Low / Low | Known in SETTINGS-AND-CONSTANTS; fix with #50 |

## 3. Permissions and privacy

| ID | Risk | Evidence | Existing control | Residual (L / I) | Next action |
|---|---|---|---|---|---|
| R-12 | Money fields on a card are readable by every role that reads the card | All 10 Currency fields of Card Monthly Card are permlevel 0 (JSON) | Reports strip ledger figures for users without GL read (`report_access.strip_ledger`); equipment rates are at permlevel 1 and 2 | Medium / Medium | FR-007 (Planned): move money to a protected level |
| R-13 | Whoever creates a monthly card can also submit it | No separation-of-duties check in `card_monthly_card.py` | Applies to transport financial decisions, needs reviews, fitment and custody already | Medium / Medium | FR-006, #51 |
| R-14 | Card Settings is a Single: a reader of level 1 receives the rows of every company | CHANGELOG [Unreleased], review M3 (diesel schedule) and `company_settings` | Form hides other companies' rows; REST and report view do not | Medium / Medium | Per-company settings storage or a server filter (#50) |
| R-15 | Cross-company leakage through links, shares or Versions | History: registry aggregates (#23), Version masking, `deny_cross_company_share` | `permission_query_conditions` / `has_permission` on 9 DocTypes and `permission_query_conditions` on 5; tests named in [07-international-test-matrix.md](07-international-test-matrix.md) | Low / High | Add a company-isolation test for each new DocType in the PR that adds it |
| R-16 | Whitelisted method with a wrong HTTP method | `AGENTS.md` rule; `test_read_endpoints_get_only.py` | Test over read endpoints | Low / Medium | Extend the test to assert POST on every writer (#54) |
| R-17 | Roles used by code are not all shipped as fixtures | Fixtures ship `Card Manager`, `Card User`; code also uses `Card Supervisor`, `Card Operator` (created by patches `v1_2.ensure_card_roles`, `v4_0_0.ensure_materials_roles`) | Patches are idempotent | Low / Low | Confirm in the role matrix ([ROLE-ACTION-MATRIX.md](../governance/ROLE-ACTION-MATRIX.md)) |

## 4. Data model and operations

| ID | Risk | Evidence | Existing control | Residual (L / I) | Next action |
|---|---|---|---|---|---|
| R-18 | Machine status has no transition rule | `card_equipment.py` has no status check; only `equipment_status.py` for new use | Per-company Warn or Refuse; defaults to Warn | Medium / Medium | Keep Warn as default; choose Refuse per company at go-live (#120) |
| R-19 | Derived location can be empty or wrong when assignments overlap or the daily sync is off | `transfer.sync_equipment_location`; setting `sync_equipment_location_daily` | Overlap refused on write under a lock; conflicts leave a comment and empty the field rather than guess | Low / Medium | Run the unit integrity check (`get_unit_integrity_issues`) and the assignment reports at go-live (#122) |
| R-20 | Period lock covers three DocTypes by date only | `card/period_lock.py`; hooks | Override role is logged and notified | Medium / Medium | Decide whether needs, custody and assignment need a lock; align with ERPNext accounting period (#119) |
| R-21 | Arabic text is the stored value of many Selects | See [04-localization-matrix.md](04-localization-matrix.md) | Constants in `constants.py` | Medium / Medium | Any integration, script or report filter must use the stored value; do not rename a value without a patch |
| R-22 | Diesel is litres only | Field names and labels | None | Low / Medium for a non-litre company | #46, #47 |
| R-23 | Both `internal_rate` and `internal_hourly_rate` exist | `card_value.internal_rate_of` | New field wins | Low / Low | Retire the older field with a patch when the owner approves |
| R-24 | The Transport has two sets of location fields | `from_location` / `to_location` and `source_*` / `destination_*` in JSON; posting query selects both | `description` code falls back across them | Low / Low | Retire the older pair in a later cleanup |
| R-25 | A direct database edit of a source's invoice link can split the source from its posting log | Links are written by `db.set_value` with `update_modified=False` | Submit-time `_verify_sources`; reports | Low / High | Add a read-only integrity report that lists sources whose link and log disagree (#54) |

## 5. Quality and delivery

| ID | Risk | Evidence | Existing control | Residual (L / I) | Next action |
|---|---|---|---|---|---|
| R-26 | No multi-currency or two-company posting test | No test builds a posting for a company whose currency differs from the site default, or two companies side by side | Single-company posting tests (`test_s3_posting.py`, `test_posting_lines.py`) | Medium / High for a second company | Build the international matrix ([07-international-test-matrix.md](07-international-test-matrix.md)) |
| R-27 | The mobile app (`frontend/`) is a second permission surface | `card/mobile.py`, `card/www/cdms`, `test_mobile.py` | Server-side permission checks; read endpoints GET only | Low / Medium | Mobile role-based navigation is Planned (FR-059) |
| R-28 | Print fonts install into the bench user's home | `card/fonts.py` | Best-effort, logged, falls back to DejaVu | Low / Low | Verify on each new server |
| R-29 | Skills required by `AGENTS.md` may be missing in a session | `docs/governance/SKILL-SUBSTITUTES.md` | Approved substitutes and a mandatory review procedure | Low / Low | None |
