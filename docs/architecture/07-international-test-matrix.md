# International test matrix

#54 asks for a matrix covering: two or more companies, different currencies, locale and time zone, fuel units, taxes,
roles, equipment ownership, multiple customers and supplier-specific contracts. This file lists the dimensions, what the
test suite proves today (file names under `card/tests/`), and what is missing. It started as a design for the missing tests; FR-136 (#54, branch `feat/acceptance-suite`, in
review) adds the tests of rows 1, 2, 4, 14 and 15 and the POST-only test of the writers (risk R-16).

CI today (`.github/workflows/`): `ci.yml` (`bench run-tests --app card` with coverage, and a CARD Mobile job: type check, unit tests, build), `linters.yml` (pre-commit), `codeql.yml`, `pr-title.yml`, `upgrade-rehearsal.yml` (v1.0.1 to the candidate on pinned frappe and
erpnext, migrate twice, compare), `release.yml`. The suite has about 90 test modules.

Status: **Covered**, **Partial** (covered for one company, one currency, one role set), **Missing**.

## 1. Dimensions and coverage

| # | Dimension | Cases to prove | Status | Evidence now | Gap |
|---|---|---|---|---|---|
| 1 | Companies | Two companies on one site: separate settings rows, accounts, cost centers; a user restricted to Company A cannot read or write B's equipment, cards, fills, transports, assignments, requests, custody | Covered for access | `test_card_company_isolation.py`, `test_assignment_company_isolation.py`, `test_transport_company_isolation.py`, `test_diesel_fill_company_permission.py`, `test_report_access.py`, `test_posting_access.py`, `test_bola_matrix.py`; posting for both companies in one run: `test_two_currency_posting.py` (FR-136, in review) | |
| 2 | Currency | Company A in currency X and Company B in currency Y: invoices in each company currency, rate 1; CARD amounts display in the company currency; diesel price currency limited to the company currency | Covered for posting and reports; Partial for forms (FR-136, in review) | `test_diesel_price_schedule.py` (currency defaults to the company currency, a foreign one is refused); `test_two_currency_posting.py` (same supplier in two companies: each invoice only its company's sources, in its currency at rate 1, own payable, expense accounts, cost centers and project; ledger rows in the company currency; report currency label) | Forms: card and fill amount fields have no currency option, so they show the site default symbol. Reports: a total row keeps the site default symbol, and server-side formatting (export, print) of the multi-company Equipment Consumption uses one currency for all rows. Policy O-17: company currency only, no conversion |
| 3 | Language | UI in Arabic, English and one other language; prints in LTR and RTL; amount in words in each | Partial | `test_i18n.py` (app name in every language), `test_print_formats.py`, `test_print_defaults.py`, `frontend/src/i18n.spec.ts` | No test renders a print in a third language; Arabic-only translation of CARD strings |
| 4 | Time zone and dates | Site zone differs from the company's: "future day" check, month boundaries, period lock date, daily sync, posting date = last day of month | Covered (FR-136, in review) | `test_period_lock.py`; `test_month_end_timezone.py` (one UTC instant that is 1 October in UTC+3 / UTC+14 and 30 September in UTC-7 / UTC-10: site-local today, future-day check, "last month", 28/29/30/31 month ends, posting dated the month end after local midnight, lock boundary by date) | No per-company time zone (one site zone); the daily location sync uses the same site date |
| 5 | Fuel unit | Litres, and a company that bills another unit | Missing | Diesel tests are in litres (`test_diesel_*`) | Blocked by design: no unit setting (#46, #47) |
| 6 | Tax | Supplier with and without a tax identifier; single-rate template; zero-rate line; multi-rate template refused; VAT basis Inclusive and Exclusive; customer deduction as discount; non-taxable deduction refused | Covered for one regime | `test_s3_posting.py`, `test_posting_lines.py`, `test_p0_posting_integrity.py`, `test_posting_preview.py`, `test_s3_config.py` | A regime where sales can be untaxed; a second rate |
| 7 | Roles | Each role can and cannot do each action; separation of duties | Partial | `test_permissions.py`, `test_settings_permlevel.py`, `test_equipment_financial_privacy.py`, `test_commercial_protection.py`, `test_fitment.py`, `test_v4_materials.py` | The full role-by-action table is [ROLE-ACTION-MATRIX.md](../governance/ROLE-ACTION-MATRIX.md); a generated test per row is Missing |
| 8 | Equipment ownership and direction | Owned, rented in, third party; rented-in, rented-out, sub-rental, internal; allowed direction per ownership; combined unit of owned pieces | Covered | `test_unit_ownership.py`, `test_f_rules.py`, `test_customer.py`, `test_sided_totals.py`, `test_shift_customer_rate.py`, `test_equipment_g2.py` | |
| 9 | Multiple customers | One customer per equipment and card; two customers for the same project on different machines; customer statements per company | Partial | `test_customer.py`, `test_customer_reports.py` | A project with several customers and a responsibility matrix is not in the model (#41) |
| 10 | Supplier-specific terms | Different diesel supplier policy; per-supplier registry; price exception by role | Partial | `test_diesel_price_lock.py`, `test_registry_history.py`, `test_settings_wiring.py` | Per-supplier contract terms are not in the model (#41) |
| 11 | Backdating | A card, fill or transport dated inside a closed period; a late source after a submitted invoice; transport backdated before an existing assignment | Covered in parts | `test_period_lock.py`, `test_period_lock_extra_keys.py`, `test_p0_posting_integrity.py`, `test_transfer.py` | Backdated transport across a month with a submitted posting |
| 12 | Idempotency | Second build of the same month; second migrate; second import of a diesel session; second approval click | Covered | `test_gl_posting_log_integrity.py`, `test_amended_copy_name_reuse.py`, `test_diesel_import.py`, `test_tool_handover_concurrency.py`, `upgrade-rehearsal.yml` | |
| 13 | Corrections | Cancel invoice, cancel card, amend, rebuild, credit note, accept a correctable difference | Covered | `test_p0_posting_integrity.py`, `test_s3_posting.py`, `test_settlement_phase1.py` | Credit note creation is Planned |
| 14 | Concurrency | Two writers on one assignment, one fitment row, one tool handover | Covered | `test_assignment_overlap_concurrency.py`, `test_fitment_concurrency.py`, `test_tool_handover_concurrency.py` | Two simultaneous builds for the same party-month meet the unique `posting_key` in the database: `test_gl_neutrality.py` (FR-136, in review) |
| 15 | GL neutrality | CARD documents themselves create no GL; only the submitted invoice does | Covered (FR-136, in review) | `test_o3_dimension.py`, `test_s3_posting.py`; `test_gl_neutrality.py` (static scan: no module writes GL Entry, Payment Ledger Entry, Stock Ledger Entry or Account Closing Balance; submit and cancel of card, fill, transport and the draft posting add no ledger row; the invoice submit adds only its own balanced rows); `test_posting_source_integrity.py` (R-25 report) | |
| 16 | Migration | v1.0.1 to candidate; second migrate; history preserved | Covered on synthetic data | `upgrade-rehearsal.yml`, `.github/helper/upgrade_rehearsal.sh`, `test_baseline_regression.py`, `test_app_name_translation_patch.py` | Rehearsal on production-sized data is an owner step (#119) |
| 17 | Mobile | Role-based entry, read endpoints GET only | Partial | `test_mobile.py`, `test_read_endpoints_get_only.py`, `test_writer_methods_post.py` (every writer POST only, R-16), `frontend` unit tests | End-to-end on a phone is an acceptance step (#118) |

## 2. Fixtures the missing tests need

All synthetic. None is real data.

| Fixture | Content |
|---|---|
| Company A | Currency X, single-rate purchase and sales tax templates, own accounts and cost center, Card Company Settings row |
| Company B | Currency Y, different tax rate, own settings row, a different time zone set at site level for the zone cases |
| Users | One per role (Card Manager, Card User, Card Supervisor, Card Operator, Accounts Manager, Stock Manager) restricted to Company A, and one restricted to B |
| Parties | Supplier X (with tax identifier), Supplier Z (without), Customer Y, Transporter T |
| Equipment | Owned, rented in, sub-rental, one combined unit, one ended machine |
| Documents | A month of cards, fills and transports on two projects, including a late source and a backdated transport |

## 3. Suggested order

1. GL neutrality test (row 15) and the `ignore_permissions` allow-list test (risk R-06): done (FR-136 in review; FR-129).
2. Two-company posting run with two currencies (rows 1, 2, 6): done (FR-136, in review).
3. Time zone and month-end cases (row 4): done (FR-136, in review).
4. Generated role-by-action tests from [ROLE-ACTION-MATRIX.md](../governance/ROLE-ACTION-MATRIX.md) (row 7).
5. Fuel unit and multi-customer rows wait for #46, #47 and #41.
