# CARD equipment model vs Frappe HR employee model — parity review

**Status: read-only review (documentation only).** Issues #54 (quality: HRMS parity audit) and #40 (architecture:
HRMS v16 gap analysis). Nothing here changes code. CARD does not depend on HRMS and must not (AGENTS.md: depends
on `frappe` and `erpnext` only); this file compares designs, it does not propose importing HRMS code.

## 0. Sources and baseline

- CARD: `main` @ `1b7c20d` (v4.5.0). Paths are relative to the repository root.
- Frappe HR: official repository https://github.com/frappe/hrms, branch `version-16` @ `3b7f8f2` (shallow clone,
  2026-11-10). Paths below starting with `hrms/` are in that repository.
- Frappe HR documentation: https://docs.frappe.io/hr (pages named in each row).
- The Employee DocType itself is defined by ERPNext; HRMS extends it (`hrms/hooks.py:160` overrides the class with
  `hrms.overrides.employee_master.EmployeeMaster`, `hrms/hooks.py:215-226` adds its document events).
- No forum, blog or third-party source was used.

Status legend: **Equivalent** (same guarantee, CARD's own design) · **Partial** · **Gap** (HRMS has it, CARD does
not, and the CARD domain needs it) · **N/A** (no equipment meaning).

## 1. Lifecycle

| HRMS concept (source) | CARD equivalent (file / DocType) | Status | Evidence and notes |
|---|---|---|---|
| Employee master with status Active / Inactive / Suspended / Left and relieving date ([Employee](https://docs.frappe.io/hr/employee)) | `Card Equipment` (`card/card/doctype/card_equipment/`), `status` نشطة / متوقفة / في الصيانة / منتهية, `exit_reason`, `settlement_status` | Partial | The status is a plain field: no controller rule stops an ended machine from getting a new assignment or card (no status check in `card_equipment.py`; `materials.py:28,53` reads `ENDED_STATUS` for requests only). HRMS refuses attendance for an inactive employee (`hrms/hr/doctype/attendance/attendance.py:155` `validate_employee_status`) |
| Onboarding from a job applicant / offer ([Employee Onboarding](https://docs.frappe.io/hr/employee-onboarding); `hrms/hr/doctype/employee_onboarding/employee_onboarding.py:18`) | Create from Asset (`card/api.py:362` `create_equipment_from_asset`, FR-095); Asset Mapping Review report | Equivalent | Minimum-input creation from the Asset, one Asset per equipment (FR-095, `test_asset_mapping.py`) |
| Unique identity per employee | Chassis and plate unique per company (FR-080, `card_equipment.py:58-60`, `test_equipment_identity.py`) | Equivalent | — |
| Promotion: dated change of grade / designation, history kept ([Employee Promotion](https://docs.frappe.io/hr/employee-promotion); `hrms/hr/doctype/employee_promotion/employee_promotion.py:24`) | Commercial changes on Card Equipment need a reason, fields at permlevel 1 / 2, Version history (FR-019, FR-096) | Partial | History exists (Version), but rates are not dated: a new rate applies to every later card (dated agreements postponed, CHANGELOG `[Unreleased]` "Dated rate agreements") |
| Work history updated on transfer / promotion (`hrms/hr/utils.py:58` `update_employee_work_history`) | Assignment periods (`Card Equipment Assignment`) written by transports (`card/transfer.py:307` `apply_transfer`, `:470` `reverse_transfer`) | Equivalent | The assignment table is the history; a cancel undoes only what that transport wrote (FR-073, `test_transport_item_rows.py`) |
| Separation with checklist ([Employee Separation](https://docs.frappe.io/hr/employee-separation); `hrms/hr/doctype/employee_separation/employee_separation.py:12`) | Return to supplier by Equipment Transport; `exit_reason` on equipment | Partial | No exit document with a checklist (final card, last diesel, custody returned) |
| Full and final settlement (`hrms/hr/doctype/full_and_final_statement/`) | Settlement phase 1 (FR-110, `card/gl/journal_link.py:30`, Card Settlement Status report) | Partial | Links accrual Journal Entries to cards; no end-of-rental settlement document |

## 2. Assignment

| HRMS concept | CARD equivalent | Status | Evidence and notes |
|---|---|---|---|
| Employee Transfer between branches / companies, submitted, cancel reverses ([Employee Transfer](https://docs.frappe.io/hr/employee-transfer); `hrms/hr/doctype/employee_transfer/employee_transfer.py:21,50`) | `Equipment Transport` (submittable) moving each row to a project, workshop, storage or supplier (`card/transfer.py:307-365`) | Equivalent | Cancel checks (`transfer.py:373` `check_cancel_allowed`); company isolation (FR-072). A move between companies is not supported; HRMS can create a new employee in the new company (`employee_transfer.py:30-33`) |
| Shift Assignment with overlap check, submittable ([Shift Assignment](https://docs.frappe.io/hr/shift-assignment); `hrms/hr/doctype/shift_assignment/shift_assignment.py:76` `validate_overlapping_shifts`) | `Card Equipment Assignment` (not submittable) with `validate_no_overlap` (`card_equipment_assignment.py:96-110`), row lock against concurrent writers | Equivalent | FR-075, `test_assignment_overlap_concurrency.py`. CARD is stricter under concurrency (locking read on the equipment row) |
| Multiple shift assignments allowed by a setting (`HR Settings.allow_multiple_shift_assignments`, `shift_assignment.py:88-90`) | Day and night cards are separate documents (FR-017); one assignment per machine at a time | N/A | Equipment is in one place at a time |
| Effective date of a transfer | Move-day rule: the new assignment starts the day after the transport (`transfer.py:351`) | Partial | Owner decision pending (#43, #121, #122, WP-15) |
| Payroll cost centers per employee (`hrms/payroll/doctype/salary_structure_assignment/salary_structure_assignment.py:95` `set_payroll_cost_centers`) | Cost center from the assignment, then the project (`card/gl/posting.py:186` `resolve_cost_center`, `:243` `card_cost_center`) | Equivalent | FR-091, `test_p1_cost_allocation.py`. A missing or conflicting allocation refuses the build |

## 3. Attendance and card days

| HRMS concept | CARD equivalent | Status | Evidence and notes |
|---|---|---|---|
| Attendance per employee per day, submittable, status Present / Absent / On Leave / Half Day / Work From Home ([Attendance](https://docs.frappe.io/hr/attendance); `hrms/hr/doctype/attendance/attendance.json`) | `Card Monthly Card` (submittable) with one `Card Monthly Card Day` row per date; `day_status` عمل / إجازة / عطل / توقف من العميل | Partial | Card days carry hours, not only a status. Non-work days are forced to 0 hours (`card_monthly_card.py:193-194`). The status list is fixed (#45, WP-09) |
| Duplicate attendance refused (`attendance.py:72` `validate_duplicate_record`) | Duplicate card guard on equipment + project + month + year + shift (`card_monthly_card.py:315-334`); duplicate date inside a card refused (`:186-189`) | Equivalent | — |
| No attendance outside employment / for a future date (`attendance.py:60` `validate_attendance_date`) | Card days must lie inside an assignment of the card's project (`card/transfer.py:550` `validate_card_days`); no hours on a future day; back-entry only in the current fiscal year (`card_monthly_card.py:443`) | Equivalent | — |
| Attendance vs leave conflict (`attendance.py:159` `check_leave_record`) | Downtime reasons with responsible party | Gap | No downtime master or responsible party (#45, FR-009 removed) |
| Employee Checkin from device or mobile with time, device id and geolocation (`hrms/hr/doctype/employee_checkin/employee_checkin.json`; [Employee Checkin](https://docs.frappe.io/hr/employee-checkin)) | Diesel meter photos with photo times and place (FR-085); no daily operating log | Gap | Daily operator input is FR-022 (planned, blocked); provenance design in [INTAKE-PROVENANCE-DESIGN.md](INTAKE-PROVENANCE-DESIGN.md) |
| Auto attendance from check-ins ([Auto Attendance](https://docs.frappe.io/hr/auto-attendance)) | None | Gap | Depends on FR-022 |
| Attendance Request / correction with approval | Card edit before submit; cancel and amend | Partial | No card review flow (FR-011 removed; governance G1, #35) |
| Overtime (`hrms/hr/doctype/overtime_slip/`) | Overtime hours | Gap | FR-008 removed, restore after review |

## 4. Payroll and posting

| HRMS concept | CARD equivalent | Status | Evidence and notes |
|---|---|---|---|
| Payroll Entry creates Salary Slips for a period (`hrms/payroll/doctype/payroll_entry/payroll_entry.py:270` `create_salary_slips`; [Payroll Entry](https://docs.frappe.io/hr/payroll-entry)) | `card.gl.posting.post_month` / `build_monthly_posting` (`card/gl/posting.py:1008`, `:535`) build one draft Purchase Invoice per supplier and one Sales Invoice per customer per month | Partial | No Desk screen or preview (FR-004 "Implemented, not visible"; WP-13) |
| Payment days from attendance (`hrms/payroll/doctype/salary_slip/salary_slip.py:462` `get_working_days_details`, `:510` `payroll_based_on == "Attendance"`; [Working days calculation](https://docs.frappe.io/hr/working-days-calculation-in-the-salary-slip)) | Card amount = billable hours × hourly rate from the rate basis (`card_monthly_card.py:422` `_hourly_for`; FR-016) | Equivalent | — |
| Salary structure snapshot on the slip | Card snapshots at submit (`card_monthly_card.py:503-525`) | Equivalent | — |
| Accrual Journal Entry from submitted slips (`payroll_entry.py:580` `make_accrual_jv_entry`) | CARD writes no GL and creates standard ERPNext documents; accrual JEs made by accountants can be linked to cards (FR-110) | Equivalent by design | AGENTS.md engineering rule; `test_settlement_phase1.py` |
| Cancel of the payroll cancels linked entries (`payroll_entry.py:170`) | Rebuild deletes and recreates the draft; integrity checks of edited drafts (FR-090) | Partial | Manual edits on a rebuilt draft are lost (FR-004 note) |
| Additional Salary / deductions | Card adjustments (additions / deductions per company, `card/adjustments.py`) | Equivalent | — |
| Period lock: payroll period | Card period lock with override role (`card/period_lock.py:38` `enforce`, FR-050) | Partial | Override is a log line only (`period_lock.py:58-67`, WP-07) |

## 5. Permissions

| HRMS concept | CARD equivalent | Status | Evidence and notes |
|---|---|---|---|
| App access check (`hrms/hooks.py:19` `check_app_permission`) | Desk apps screen entry and roles (`card/install.py:52-54`) | Equivalent | — |
| User Permission on Employee and Company limits HR records | Company isolation through `has_permission` and query conditions (`card/hooks.py:137-158`) for assignment, card, transport, fitment, parties | Partial | Project Diesel Fill has no record-level `has_permission` (PR #161 open); 8 whitelisted functions without `methods=` (PR #161) |
| Self-approval prevention (`HR Settings.prevent_self_leave_approval`, `hrms/hr/doctype/leave_application/leave_application.py:936-950`) | None for cards | Gap | FR-006 planned; reviewer ≠ approver on materials by role only (FR-005, WP-20) |
| Salary privacy (salary slips readable by HR roles) | Money fields on equipment at permlevel 1 / 2 and masked in Version history (FR-096, `card/field_privacy.py`) | Partial | Card amounts are permlevel 0 (FR-007 planned) |

## 6. Settings

| HRMS concept | CARD equivalent | Status | Evidence and notes |
|---|---|---|---|
| HR Settings (single): `standard_working_hours`, notifications, self-approval, multiple shifts, mobile check-in ([HR Settings](https://docs.frappe.io/hr/hr-settings); `hrms/hr/doctype/hr_settings/hr_settings.json`) | Card Settings (single), shift limits, standard month hours, notifications, roles | Equivalent | Inventory in [SETTINGS-AND-CONSTANTS.md](SETTINGS-AND-CONSTANTS.md) |
| Payroll Settings: `payroll_based_on`, unmarked attendance policy ([Payroll Settings](https://docs.frappe.io/hr/payroll-settings)) | Card Company Settings per company (accounts, items, tax, diesel price, VAT basis) | Equivalent | CARD settings are per company where accounting needs it; HRMS settings are site-wide |
| Dated policies (Salary Structure Assignment `from_date`, Leave Policy Assignment) | Dated rates and prices | Gap | Only snapshots; FR-035 (dated diesel price) planned; dated rate agreements postponed |

## 7. Reports

| HRMS report (`hrms/hr/report/`) | CARD equivalent (`card/card/report/`) | Status |
|---|---|---|
| Monthly Attendance Sheet | Monthly cards list and statements (`equipment_supplier_statement`, `equipment_customer_statement`) | Partial: no day-grid report across equipment |
| Employee Analytics, Employee Information | `equipment_make_model_values`, `asset_mapping_review` | Partial |
| Employee Hours Utilization based on Timesheet | `equipment_consumption`, `operating_cost_by_project`, `equipment_meter_reconciliation` | Equivalent |
| Shift Attendance | — | Gap (depends on FR-022) |
| Project Profitability | — | Gap (#53, WP-16 partial contribution margin) |
| Employee Exits | — | Gap (no exit document) |
| Unpaid Expense Claim, Employee Advance Summary | `card_settlement_status` (FR-110), `transport_accounting_review` | Partial |

## 8. Upgrade and migration rehearsal (#54)

| Item | Evidence |
|---|---|
| Workflow | `.github/workflows/upgrade-rehearsal.yml` (PR #130): installs CARD `v1.0.1` (input `from_ref`) on frappe `v16.55.2` / erpnext `v16.54.0` (raised from 16.51.1 / 16.50.0 by the `ci/upgrade-rehearsal-current-platform` change) with MariaDB 10.6, seeds synthetic data, upgrades to the code under test, runs `migrate` twice and compares (`.github/helper/upgrade_rehearsal.sh:62-69`, `upgrade_rehearsal.py` `seed`, `snapshot`, `compare`) |
| When it runs | On every pull request (path filter removed: about 5 minutes, in parallel with the unit tests) and on manual dispatch. Before the `ci/upgrade-rehearsal-current-platform` change it ran only for patches, DocType JSON, fixtures, `install.py`, `hooks.py` and the rehearsal files |
| Recent runs (GitHub Actions) | 42696233347 on `857fd48` (PR #182, v4.5.0 content): success · 42625079640 on `a53a1a0` (PR #175): success · 42610231268 on `de3643d` (PR #172): success, after 42609616038 on `35439b4` failed and was fixed in the same pull request · 42706530545 on `ff2b919` (PR #161, open): success |
| Gap | Closed by the `ci/upgrade-rehearsal-current-platform` change (pins = the Production platform of 2026-11-10 in `docs/releases/DEPLOYMENTS.md`: frappe 16.55.2, ERPNext 16.54.0). Re-raise the pins after each Production platform update |
| HRMS on the rehearsal site | Not installed, which matches the dependency rule |

## 9. Summary of gaps

| Gap | Related issue / FR | Blocked by |
|---|---|---|
| Equipment status not enforced (ended machine can still be assigned and carded) | #42, FR-122 (In review: warn by default, Refuse per company) | Diesel fills not guarded yet |
| Dated rates, prices and policies | #46, #50, FR-035 | — (FR-035), owner (agreements) |
| Downtime reasons and responsible party | #45, FR-009, WP-09 | FR-020 decision |
| Daily operating log and check-in-like intake | FR-022, #52 | Owner decision |
| Card review flow and self-approval guard | FR-006, FR-011, #35 | G1 GO |
| Exit document and end-of-rental settlement | #42, #49 | — |
| Profitability and shift-level reports | #53 | WP-16 |
| Card amounts privacy | FR-007 | Design |
| Rehearsal pins older than Production platform | #54 | — |

Not covered by this review: the international test matrix (several currencies and locales) and the risk register
of #54, and the owner sign-off on the domain model. They remain open.
