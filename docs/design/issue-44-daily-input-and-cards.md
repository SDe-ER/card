# Issue 44: daily input and monthly cards — design

**Status: Draft design. The slice of section 3 is implemented as FR-188 (owner instruction 2026-11-25). The
rest is design only.**

- Source checked: `main` @ `b27be391` (`card/__init__.py` `__version__` = 4.11.0).
- Issue: #44 "daily input, monthly cards, project splits and automatic/manual generation". Parent: #40.
- Owner decisions on the issue: 2026-11-10, the part that depends on commercial agreements (#41, FR-023) is
  postponed. 2026-11-24, the issue is deferred (`docs/architecture/08-roadmap.md` section 5).
- This design is the "design first" step that the issue asks for. Owner instruction 2026-11-25: implement the
  concrete part behind a setting that defaults to off. That part is section 3. No other part starts without the
  owner's GO.
- "Not verified" marks a fact that was not checked in the code for this document.
- No test was run for this document. Each status below comes from reading the source at `b27be391`, before
  FR-188. Section 3 records what FR-188 changed.

## 1. Scope of the issue, item by item

Status values: **Implemented** (present in the code), **Partly**, **Not implemented**. "Implemented" does not
mean released or live. The registry owns release status.

### 1.1 Requirements

| # | Item of the issue | Status | Evidence in the code |
|---|---|---|---|
| 1 | Daily input of work | Partly | FR-142. DocType `Card Daily Log` with rows `Card Daily Log Row` (`day_hours`, `night_hours`, `stop_reason`, `stopped_hours`). Rules in `card/daily_log.py` `validate_log`, approval in `check_transition`. Gaps: the row has no load count, and the log has no intake source (paper, WhatsApp) |
| 2 | Office enters the daily work | Partly | `Card Daily Log` DocPerm: Card Manager, Card Supervisor and Card Operator create. Card User reads only. An office user with only Card User cannot enter a log. A new grant needs an owner decision |
| 3 | Mobile entry of the daily log | Implemented | FR-150. `frontend/src/pages/DailyLogForm.vue`, `DailyLogList.vue`, `DailyLogView.vue` are on `main`. The registry row FR-150 says "In review". The registry needs a correction (out of scope here) |
| 4 | Manual monthly card entry | Implemented | `card/card/doctype/card_monthly_card/card_monthly_card.py` `CardMonthlyCard.before_validate` |
| 5 | Generation of cards from daily records | Partly | FR-145. `card/daily_log_generation.py` `generate_monthly_cards` (POST). A user starts each run with the button in `card_daily_log.js`. There is no scheduled run. `_day_values` copies hours and stop data. It copies no loads |
| 6 | One card per equipment, project and month | Implemented | Duplicate check at the end of `CardMonthlyCard.before_validate`. The key is equipment, month, year, shift and project. Shift is part of the key: a day card and a night card are two cards |
| 7 | Card key includes the commercial agreement | Not implemented | Postponed by the owner on 2026-11-10 with #41 |
| 8 | Separate cards when a machine changes projects in the month | Implemented | `CardMonthlyCard._resolve_project` and `card/transfer.py` `validate_card_days`. Test `card/tests/test_daily_log_generation.py` `test_two_projects_get_one_card_each` |
| 9 | Hourly, daily and monthly billing | Implemented | `CardMonthlyCard._hourly_for`. Full-day basis: FR-138, `card/card_value.py` `bills_full_days` |
| 10 | Quantity billing, customer side | Implemented | FR-166. `before_validate`: `loads_total * load_volume_m3 * customer_rate` when `customer_rate_type` is `PER_VOLUME_M3` |
| 11 | Quantity billing, supplier side | Not implemented | FR-010. Card Equipment `rate_type` has three options: per day, per hour, per month. Test `card/tests/test_volume_billing.py` `test_per_m3_supplier_side_keeps_its_own_rate` |
| 12 | Overtime | Not implemented | FR-008. No overtime field or rule in `card/`. The only matches of the word are row descriptions in `card/tests/test_adjustments_grid.py`. Today each recorded hour is billed at the normal rate, and the shift limit only warns (`before_validate`, `over_shift_limit`) |
| 13 | Additions and deductions | Implemented | `adjustments` loop in `before_validate`. Configured types: `configured_adjustment_types` (FR-173) |
| 14 | Billing under effective contracts | Not implemented | FR-141 gives the data model: `Card Rate Agreement` and `card/agreements.py` `resolve`. No card or posting code calls `resolve`. Postponed with #41 |
| 15 | Project from the approved movement on the work date | Implemented | `card/transfer.py` `assignment_projects`, `_assigned_on`. The move day follows `Card Company Settings.move_day_rule` (`move_day_to_destination`) |
| 16 | Supplier and bill-to from effective agreements | Not implemented | The supplier comes from the equipment (`eq.supplier`) and the customer from `default_customer` in `before_validate`. Postponed with #41 |
| 17 | Approved snapshots are kept | Implemented | `CardMonthlyCard._snapshot_settings_used` writes `hourly_rate_used`, `customer_rate_used`, `load_volume_used`, `direction_used`, `customer_used`, `rate_basis_used`, `day_billing_basis_used` on submit |
| 18 | No duplicate card across the manual and automatic routes | Partly | The generation saves through `insert()` and `save()`, so the same check runs. The generation locks the equipment row (`generate_monthly_cards`, `_month_cards(lock=True)`). The manual check reads without a lock: `card_monthly_card.py` has no `for_update`. Two manual saves at the same moment are not covered. No test for that case was found |
| 19 | No overlapping periods | Implemented | A card always covers the whole month (`from_date`, `to_date` set in `before_validate`). Day rows of two projects stay apart through the assignments. Assignments cannot overlap: `card_equipment_assignment.py` `validate_no_overlap` |
| 20 | Audited amendments | Implemented | Cancel reason: `card/cancel_reason.py` `before_cancel` (FR-123). Preparers across the amendment chain: `card/governance.py` `card_preparers` (FR-143). Daily log: `card/daily_log.py` `log_preparers`, `check_cancel` |

### 1.2 Acceptance cases

| Case | Status | Evidence |
|---|---|---|
| Two projects in the same month | Implemented | `test_two_projects_get_one_card_each` |
| Transfer on a date boundary | Implemented | `card/transfer.py` `move_day_to_destination` and `validate_card_days`. Tests in `card/tests/test_transfer.py` (test names not verified) |
| Yard periods | Implemented | `card/daily_log_generation.py` `_kept_days` reports the day as `off_project`. Tests `test_yard_days_are_left_out`, `test_all_yard_days_make_no_card` |
| Repeated import | Implemented | `test_repeat_run_changes_nothing_and_a_later_log_fills_its_day`. Day-row source keys: `card/intake.py` `_check_day_intake_dedupe` (FR-158) |
| Conflicting contract | Not implemented | `card/agreements.py` `resolve` raises `AmbiguousAgreementError`, but nothing calls it for a card |
| Cross-company access | Implemented | `has_card_permission` in `card_monthly_card.py`. `_authorize` in `daily_log_generation.py`. Test `test_cross_company_is_refused` |
| Billing integrity | Implemented | `card/gl/posting.py` `_assert_identity` compares the invoice lines with the card net amount. The run of that check was not verified for this document |

## 2. Design for the items that are not fully implemented

Rules for every design below:

- Existing DocTypes first. No new DocType. No change to Frappe or ERPNext.
- CARD writes no GL entry. The monthly posting (`card/gl/posting.py` `build_monthly_posting`) makes draft
  invoices from `net_amount` and `customer_net_amount`. A person submits each invoice in ERPNext.
- No new role grant. Money fields are permlevel 1.
- A new field has an empty or "off" default. A submitted card is never priced again.
- Each change needs a CHANGELOG entry, a registry row, the "What's new" pages and tests (`AGENTS.md`).

### 2.1 Loads on the daily log (items 1 and 5)

**Problem.** A machine billed per m³ needs loads on each working day (`Card Monthly Card Day.loads_count`). The
daily log row has no load field. A card that the generation makes for such a machine has hours and zero loads, so
its customer amount is zero until a person types the loads on the card.

**Data.**

| DocType | Field | Type | Notes |
|---|---|---|---|
| Card Daily Log Row | `day_loads` | Int | Non-negative. Permlevel 0. A count, not money |
| Card Daily Log Row | `night_loads` | Int | Non-negative. Permlevel 0 |
| Card Company Settings | `daily_log_loads` | Check, default 0 | Permlevel 1, as each field of that table |

Two fields are necessary because a card is per shift, and the night card can use a different rate
(`customer_rate_night`).

**Rules, setting ON.**

1. `validate_log` refuses negative loads and loads on a future date. These are the card rules.
2. `validate_log` refuses loads on equipment whose `customer_rate_type` is not per m³. The card refuses such
   loads at a later step ("Loads can be recorded only on a card whose customer rate type is per m³"). An early
   refusal on the log is easier to correct.
3. `_day_values` adds `loads_count`: `day_loads` for the day card, `night_loads` for the night card.
4. `_shift_has_hours` also counts loads, so a night with loads and zero hours gets its card. The card permits
   loads with zero hours (FR-166).
5. A log row with loads greater than zero sets the loads of the card day. A changed value is listed in
   `overwritten_days` with the old and the new loads.
6. A log row with zero loads replaces the loads of a card day only when the day came from a different daily log
   (the notes of the day name that log). A hand-entered load count on a day that no log wrote is kept.
7. `_clear_stale` also clears `loads_count` when it clears a day.

Rule 6 is necessary because logs approved before the setting was switched on have zero loads. Without rule 6 a
new run erases loads that the office typed on draft cards.

**Amount.** No change. `CardMonthlyCard.before_validate` computes the amount from `loads_count`.

**Posting.** No change. The generation makes draft cards only.

**Permissions.** No new grant. The roles that write a daily log today write the two fields. An operator sees no
price: loads are counts at permlevel 0, as `total_loads` on the card.

**Migration.** `bench migrate` adds three columns. No patch. Existing logs get 0. Existing cards do not change.

**Tests.** See section 3.

### 2.2 Supplier-side quantity billing (item 11, FR-010)

**Data.**

| DocType | Field | Change |
|---|---|---|
| Card Equipment | `rate_type` | New option per m³ (the same stored value as `customer_rate_type` uses) |
| Card Monthly Card | `rate_type` | No change (Data, read only, mirrored) |
| Card Monthly Card | `supplier_volume_m3` | New Float, read only, permlevel 1, as `total_volume_m3` |

The design uses the existing `loads_count` on the day row and the existing `load_volume_m3` on the equipment.
One load count for the two sides is the smallest model.

**Rules.**

1. Supplier amount = total loads × load volume × supplier rate per m³, before VAT. Hours and billable stops add
   nothing. This is the customer rule of FR-166.
2. The check `loads_total and self.customer_rate_type != PER_VOLUME_M3` in `before_validate` permits loads when
   one of the two sides is per m³.
3. `_snapshot_settings_used` stores `load_volume_used` when one of the two sides is per m³, and stores the
   supplier rate per m³ in `hourly_rate_used`. `rate_basis_used` tells the two meanings apart.
4. `card/transfer.py` `is_billed_day` and its callers decide with `include_loads` if a loads-only day is a billed
   day. Each supplier-side caller needs a review. Test `test_supplier_side_day_rule_ignores_loads` records the
   rule of today.

**Amount.** `CardMonthlyCard.before_validate`, in the supplier block, next to the `bills_full_days` branch.

**Posting.** No change to the code. The purchase invoice line is built from `net_amount` with quantity 1
(`card/gl/posting.py` `_card_lines`, `_invoice_item`). The period-run fingerprint includes the load fields
(FR-177).

**Permissions.** No new grant. `rate_type` and `rate` are permlevel 1 commercial fields on Card Equipment.

**Migration.** No patch. No equipment has the new option until a Card Manager sets it. A draft card changes only
when its equipment gets the new option. A submitted card does not change.

**Tests.** Amount for day and night cards. Stops add nothing. A sub-rental card with the two sides per m³. A
sub-rental card with one side per m³ and one per hour. Submitted card not priced again after an equipment change.
Money hidden without permlevel 1. Statement and print columns. Period-run fingerprint. Existing hourly, daily and
monthly supplier amounts unchanged.

**Blocked by:** owner decisions 2 and 3 in section 4.

### 2.3 Overtime (item 12, FR-008)

**Today.** Each recorded hour is billed at the normal hourly rate. A day above the shift limit only warns. With
the "Full day" basis a day is billed as one day for any number of hours.

**Data.**

| DocType | Field | Type | Notes |
|---|---|---|---|
| Card Equipment | `overtime_factor` | Float, permlevel 1 | Supplier side. Empty or 1 = no overtime premium (today) |
| Card Equipment | `customer_overtime_factor` | Float, permlevel 1 | Customer side. Empty or 1 = today |
| Card Monthly Card | `overtime_hours` | Float, read only, permlevel 0 | Hours above the threshold, summed over the days |
| Card Monthly Card | `overtime_amount`, `customer_overtime_amount` | Currency, read only, permlevel 1 | The premium only |
| Card Monthly Card | `overtime_factor_used`, `customer_overtime_factor_used` | Float, read only, permlevel 1 | Submit snapshot |

The two factors are commercial terms. They follow the change-reason rule of the other commercial fields of Card
Equipment (`card_equipment.py` `validate_commercial_change_reason`. The list of fields it covers was not verified).

**Rules (proposal, each needs the owner's answer).**

1. Overtime hours of a day = working hours above the equipment's `daily_hours`. Stopped hours are not overtime.
2. Premium = overtime hours × hourly rate × (factor − 1). The normal amount does not change, so factor 1 gives
   the amount of today.
3. The premium is part of `amount` and `customer_amount`, so `net_amount`, the statements and the posting need
   no change.
4. A per-m³ side has no overtime.

**Amount.** `CardMonthlyCard.before_validate`, in the day loop (per-day hours) and in the two amount blocks.

**Posting.** No change to the code. The invoice line comes from the net amounts.

**Permissions.** No new grant.

**Migration.** No patch. Empty factors keep each amount. Submitted cards do not change.

**Tests.** Factor empty and factor 1 give the amounts of today. A day at the threshold. A day above it. Night
card. Sub-rental with different factors per side. Full-day basis. Per-month rate. Snapshot on submit. Money
hidden without permlevel 1. Generation from a daily log gives the same amount as a hand-entered card.

**Blocked by:** owner decision 4 in section 4.

### 2.4 Lock on the manual duplicate check (item 18)

**Rule.** Before the duplicate check, `before_validate` locks the Card Equipment row
(`frappe.db.get_value(..., for_update=True)`) and reads the other cards with a locking read. This is the pattern
of `card/daily_log.py` `_check_duplicates`.

**Effect.** No data change. No setting. A second save of the same key waits, then gets the existing refusal.
**Test.** Two connections, as `card/tests/test_daily_log_generation_concurrency.py` does.
**Risk.** A lock on each card save. The lock order must match the generation (equipment first).

This is a correctness fix, not a feature. It needs no business decision, but it does not fit "behind a setting".

### 2.5 Items postponed by the owner (7, 14, 16, conflicting contract)

No design here. The data model exists (FR-141). The wiring is the subject of #41 and FR-023. When the owner
reopens them, the card reads `card.agreements.resolve` on each work date and stores the agreement on the card.

### 2.6 Office entry and paper or WhatsApp source (items 1 and 2)

- A grant of create on `Card Daily Log` to Card User is a permission change. It needs owner decision 5.
- A source field on the daily log is part of #52 (intake), which the owner deferred. The card day row has the
  fields (`intake_source` and three more, FR-158). The generation does not set them: a generated day keeps the
  default `manual` and names its log in `notes`.

## 3. Smallest safe slice

**Implemented as FR-188** on branch `docs/design-issue-44` (local commits, not pushed, status "In review"). The
tests in `card/tests/test_daily_log_loads.py` were written without a bench and were not run on a site.

Differences from the plan below:

- The form reads the setting from an onload flag (`CardDailyLog.onload`), not from a new whitelisted method. A
  new daily log shows the two load fields after its first save.
- The two load fields are not grid columns. They show in the row form.
- Tests 1 and 13 are narrower: the refusal is tested on insert only, and no test covers a Card Operator and money
  fields (the change adds no money field).
- Test 12 checks `card.daily_log.loads_enabled` for two company names, not two full companies.
- The popup of **Generate monthly cards** does not show the old and new loads. The result of the method has them.

Added after the review of FR-188:

- A save that does not send the two load fields keeps the stored loads (`card/daily_log.py`
  `keep_unsent_loads`). CARD Mobile sends rows without them (`frontend/src/data/dailyLog.ts` `ROW_FIELDS`), and
  a REST update would store 0. The rule: a load field that is `None` on the row when `validate` runs was not
  sent. A sent 0 is 0. The corrected draft of CARD Mobile is a new log with `amended_from` and rows without
  names. Its unsent load fields take the value of the amended log's row of the same equipment.
- OFF after ON: a log that holds loads is saved while its loads are unchanged or cleared. Only new or changed
  loads are refused. The form shows the two fields read only on such a log.
- OFF after ON: when a day is cleared because its log was cancelled, a load count equal to the loads of that
  log's row is cleared with it (`card/daily_log_generation.py` `_clear_stale`). Another count is a hand entry
  and is kept. Limit: a hand entry equal to the loads of the cancelled log is cleared too. No field records
  the source of `loads_count`.
- The Desk form sends 0 for an emptied load field (`card_daily_log.js`, `validate`). Without it an emptied
  field is null, the server reads null as "not sent" and restores the stored loads.
- OFF after ON: a day now set from another log (the corrected log) loses a load count equal to the loads of the
  earlier log named in its notes (`_apply_days`, `_loads_of_earlier_log`). The same limit applies: an equal hand
  entry is cleared too.
- A new log takes unsent loads from the log it amends only when that log has its company, project and date
  (`_load_baselines`). A different `amended_from` gives no loads.
- Not verified on a site: the `None` rule comes from reading the Frappe `version-16` source
  (`frappe/model/document.py` `init_valid_columns`, `_save`, `insert`).

**The change: loads on the daily log (section 2.1), behind a company setting that is OFF by default.**

It needs no new business decision. The owner approved customer billing per m³ and per load (FR-166). The slice
only moves the entry of loads from the card to the daily log.

| Point | Value |
|---|---|
| Setting | `Card Company Settings.daily_log_loads`, Check, default 0, permlevel 1. Label "Loads on daily logs" |
| Read by | `card.settings.company_setting(company, "daily_log_loads")`, as `card/gl/period_gate.py` reads `require_period_approval` |
| Scope | Desk form and the generation. CARD Mobile screens are a later change |

**Behaviour when OFF (default, and when the company has no settings row):**

- The two load columns are hidden on the daily log form.
- `validate_log` refuses a log row with loads and names the setting. No route can store loads.
- The generation does not write, compare or clear `loads_count`. Its result is the result of today.
- No card amount changes.

**Behaviour when ON:** rules 1 to 7 of section 2.1.

**Files to touch.**

| File | Change | Lines (estimate) |
|---|---|---|
| `card/card/doctype/card_daily_log_row/card_daily_log_row.json` | Two Int fields | 25 |
| `card/card/doctype/card_company_settings/card_company_settings.json` | One Check field | 12 |
| `card/daily_log.py` | `validate_log`: load rules, setting check | 35 |
| `card/daily_log_generation.py` | `_approved_rows`, `_day_values`, `_shift_has_hours`, `_change`, `_apply_days`, `_clear_stale` | 45 |
| `card/card/doctype/card_daily_log/card_daily_log.js` | Show the columns when the setting is on | 20 |
| `card/locale/*.po` | New strings, each locale | 10 per locale |
| `card/tests/test_daily_log_loads.py` (new) | Tests below | 220 |
| `CHANGELOG.md`, registry, `docs/governance/SETTINGS-AND-CONSTANTS.md`, `website/` pages | As `AGENTS.md` requires | 60 |

Effort: about 140 lines of application code, about 220 lines of tests, about 60 lines of documentation.

**Tests.**

1. OFF: a log with loads is refused on form save, on REST insert and on `frappe.client.set_value` of a row.
2. OFF: a run of the generation gives the same result and the same card values as before the change, on a card
   with hand-entered loads.
3. ON: day loads go to the day card and night loads to the night card. The customer amount equals the amount of
   a hand-entered card.
4. ON: a night with loads and zero hours gets a night card.
5. ON: loads on equipment that is not per m³ are refused on the log.
6. ON: negative loads and loads on a future date are refused.
7. ON: a second run changes nothing.
8. ON: an old approved log with zero loads does not erase hand-entered loads (rule 6).
9. ON: an amended log with other loads replaces the loads and lists the day in `overwritten_days`.
10. ON: a cancelled log clears the loads of its day on a draft card and only reports on a submitted card.
11. ON: a submitted card is not changed.
12. Company A ON and company B OFF on one site: each company follows its own setting.
13. A Card Operator gets no money field through the daily log or the generation result.
14. The existing suites `test_daily_log.py`, `test_daily_log_generation.py` and `test_volume_billing.py` pass
    unchanged.

**Gates before code:** the owner reopens #44 for this slice. Then the normal gates apply: `/code-review`,
`/security-review` (data handling is touched), CI, and validation on the CARD QA site only.

**Limit of the slice.** Operators on CARD Mobile cannot enter loads until the mobile form gets the two fields.
The Desk form is enough for the office and for supervisors.

## 4. Open owner decisions

1. **Start the slice of section 3?** Decided 2026-11-25: yes. Implemented as FR-188, Desk only.
   Open: the mobile fields, and the company that switches the setting on.

2. **Is a supplier paid by quantity?** (FR-010)
   Options: (a) no, suppliers stay on hour, day or month. (b) yes, per m³ with the same loads as the customer.
   (c) yes, with a different unit (per load, per ton).
   Recommendation: (a) until a real supplier contract needs it. Then (b), which reuses the existing loads.

3. **If decision 2 is (b): the same load volume for the two sides?**
   Options: (a) one load volume per machine for the two sides. (b) a separate volume for the supplier.
   Recommendation: (a). One machine carries one volume.

4. **What is overtime, and what is its price?** (FR-008)
   Options for the start of overtime: (a) hours above the machine's daily hours, each day. (b) hours above the
   company shift limit, each day. (c) hours above the standard month hours, for the month.
   Options for the price: a factor per machine (for example 1.25) or a separate rate.
   One more question: does a machine billed by full days get overtime?
   Recommendation: (a), with a factor per machine and per side, and no overtime on full-day billing until a
   contract needs it. An empty factor keeps the amounts of today.

5. **Can an office user with only the Card User role enter daily logs?**
   Options: (a) no, the office uses Card Supervisor or Card Manager. (b) yes, grant create on the daily log.
   Recommendation: (a). It needs no permission change.

6. **Correct the lock gap of section 2.4?**
   Options: (a) yes, as a separate small fix. (b) no.
   Recommendation: (a). It changes no business rule.

## 5. Out of scope

- One card per commercial agreement, supplier and bill-to from agreements, and the "conflicting contract" case.
  Postponed by the owner with #41 and FR-023.
- Intake source (paper, WhatsApp) on the daily log. Issue #52, deferred.
- A scheduled, unattended generation of cards. The generation stays a manual action that makes drafts.
- Automatic submit of a card, and each invoice, payment or GL action. These stay human actions in ERPNext.
- Period approval before billing (#49) and separation of duties on cards (#51).
- CARD Mobile changes for loads.
- A user-defined day-status table (FR-061).
- The correction of the registry rows FR-022 and FR-150. It is a separate documentation task.
- Each change to permissions, roles, workflows or Production.
