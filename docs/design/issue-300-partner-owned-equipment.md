# Partner-owned equipment: design for issue 300

Status: design. The slice of section 4 is implemented as FR-190 (in review, not merged, not released). The rest
of this document authorizes no DocType, no permission, no posting and no migration.

Evidence: source inspection of `origin/main` at `b27be391` and of `origin/feat/crusher-owner-statement` at
`1c696736`, on 2026-11-25. No site, bench or ERP was read. Statements about ERPNext are marked "not verified" when
the installed ERPNext source was not read.

Issue state on 2026-11-25: issue 300 is open, has the label `deferred`, and has the comment "Owner decision
2026-11-24: deferred. No work on this issue until the Owner reopens it." A later owner instruction of 2026-11-25,
relayed to the implementing agent, approved the design document and the slice of section 4 behind a setting that
defaults to off. The label and the comment on the issue were not changed by this work. Each later phase needs its
own owner decision.

Terms used in this document:

- **Partner**: a person or firm, not the company, that owns a machine the company operates or bills.
- **Partner machine**: a `Card Equipment` row with `ownership` = `طرف ثالث` (`card/constants.py` `THIRD_PARTY`).
- **Entitlement**: the amount the company owes the partner for a period, before payments.
- **Card money level**: read on permlevel 1 of `Card Monthly Card` (`card/field_privacy.py` `MONEY_LEVEL`).
- **Ledger gate**: `card/report_access.py` `can_view_ledger(company)`.

## 1. Scope and what pull request 225 built

### 1.1 Scope of issue 300

The business owner wants three things:

1. To know who owns each machine.
2. To know what each partner is entitled to after deductions (operating costs, advances, salaries charged to the
   partner).
3. A partner statement.

Issue 300 holds the scope of pull request 225, which the owner closed without a merge on 2026-11-24. The issue names
three blockers: a new FR number, an owner design approval for the permissions (Salary Slip bulk read, General Ledger
read) and payables, and separate approvals for data migration and accounting.

### 1.2 State of `main` today

| Fact | Source |
|---|---|
| Ownership has three values: `ملك`, `إيجار`, `طرف ثالث` | `card/card/doctype/card_equipment/card_equipment.json` field `ownership` (Select, permlevel 1, mandatory) |
| A partner machine can only have the direction rented in or sub-rental | `card/constants.py` `allowed_directions` |
| The owner link is `supplier`, label "Lessor / Owner", a Supplier link at permlevel 1. The form shows it only for the rented-in and sub-rental directions | `card_equipment.json` field `supplier`, `depends_on` |
| Posting selects cards by direction, not by ownership. A sub-rental card is in the supplier Purchase Invoice and in the customer Sales Invoice | `card/gl/posting.py` filters on `card_direction` with `SUPPLIER_BILLING_DIRECTIONS` and `CUSTOMER_BILLING_DIRECTIONS` |
| The supplier reports include partner machines: the filter is `ownership != ملك` | `card/card/report/equipment_supplier_statement/equipment_supplier_statement.py` `execute`; `card/card/report/equipment_suppliers_summary/equipment_suppliers_summary.py` `execute` |
| Cost reports give a partner machine an internal rate | `card/card_value.py` `INTERNAL_OWNERSHIPS` |
| The beneficiary of a card is resolved only for the Supplier case. Other beneficiary types are blocked | `card/settlement.py` `VERIFIED_BENEFICIARY_TYPES`, `resolve_beneficiary`, `posting_block_reason` |
| No share, no partner record and no entitlement exists | `docs/governance/SETTLEMENT-PARTY-DESIGN.md` section 1 |

### 1.3 Pieces of pull request 225

The branch has 10 commits and changes 36 files (4,832 added lines) against `origin/main`. The pull request body
reports 35 passing tests in `card/tests/test_crusher_owner.py`. Issue 300 reports failing unit tests and 6 conflicts
on 2026-11-16. This inspection did not run the tests.

| Piece (file and function on the branch) | Verdict | Reason |
|---|---|---|
| `card/constants.py` `OWNER_MODEL_MANAGED`, `OWNER_MODEL_SELF`, `OWNER_MODELS`; `card_equipment.json` fields `owner_model`, `owner_entitlement_from`; `card_equipment.py` `validate_third_party_owner` | Reusable with changes | The field pattern is sound: both fields are commercial fields at permlevel 1 with a change reason. The validation forces the partner to be a Supplier. `SETTLEMENT-PARTY-DESIGN.md` section 4 records that the owner corrected this assumption. Keep the fields, change the party rule after decision D3. |
| `card/constants.py` `allowed_directions`: a partner machine can be rented out to a customer | Not reusable as is | A rented-out card bills the customer only. The partner then has no ERPNext document, and the entitlement exists only in a CARD report. That is a parallel record of a payable. The sub-rental direction already gives both invoices (section 2). |
| `card_equipment.py` `validate_rental_direction` change: a partner machine can wait for its customer rate; `card_monthly_card.py` `before_submit` rate check | Reusable as is, as a separate change | It is independent of the entitlement. It changes submit behavior for all customer-billing cards, so it needs its own tests and its own registry row. |
| `card/api.py` `_party_cards` and `refresh_supplier`; `equipment_supplier_statement.py` and `equipment_suppliers_summary.py` filter `card_direction != DIR_RENTED_OUT` | Not reusable | These follow from the rented-out direction above. Without that direction they do nothing. |
| `Card Owner Revenue Approval` DocType; `card/owner_statement.py` `card_approvals`, `amendment_chains`, `card_revenue`; field `Card Adjustment Type.owner_revenue` | Reusable with changes, later | The customer approval of an addition row is a real event and it does not depend on the party model. It is needed only for the revenue-share model (decision D2). It adds a DocType and permissions, so it is not part of the first step. |
| `Card Owner Deduction` DocType (submittable); `card_owner_deduction.py` `_refuse_automatic_deduction`, `_refuse_owner_ledger_source`, `_refuse_over_allocation` | Not reusable as built | It records a charge to the partner outside ERPNext. The double-charge checks exist because the same amount can also be in the ledger. A charge to a partner is an ERPNext document on the partner's ledger (section 3.3). The check ideas stay useful as report warnings. `_refuse_over_allocation` uses raw SQL with parameters (not verified beyond the grep). |
| `card/owner_statement.py` `owner_ledger`, `classify`, `_set_reversals` | Reusable with changes | They read `GL Entry` with `frappe.get_all`, and the report calls them only after `can_view_ledger`. The classification (payment, recharge, reclass, transfer, accrual, adjustment) is the core of a partner statement. They filter by a Supplier party. They must follow decision D3. |
| `card/owner_statement.py` `cost_center_expenses`, `cost_center_days`, `cost_center_share`, `deductible_expense_accounts`, `excluded_expense_accounts`, `rent_expense_accounts` | Reusable with changes | They share the expenses of a cost center between machines by working days. That is an estimate. The `Card Equipment` accounting dimension gives an exact tag per ledger row (section 2). Keep `excluded_expense_accounts` (it removes diesel and payroll accounts). Replace the working-day share when the dimension is on. `Card Equipment.cost_center` is at permlevel 2 on `main`. The branch does not show a permlevel 2 check for these figures (not verified). |
| `card/owner_statement.py` `wages_by_card`, `salary_slips`; `crusher_owner_statement.py` `can_view_wages` | Not reusable without decision D4 | They read `Salary Slip` gross pay in bulk and assign it to machines. `can_view_wages` is a careful gate (role read without owner limit, no User Permission on Employee or Salary Slip, company permitted). However, CARD reading payroll is a new data flow the owner has not approved. HRMS is also not a declared dependency of CARD (`AGENTS.md`: "Depends on `frappe` and `erpnext` only"). |
| `card/owner_statement.py` `family_members`, `family_of`; field `Card Equipment Supplier.settlement_family` (Link to Supplier Group) | Not reusable now | A family settlement is a business rule the owner has not confirmed. It reuses Supplier Group for a second meaning. Defer (section 7). |
| `card/owner_statement.py` `build_statement`, `apply_recorded`, `period`, `month_label`; `crusher_owner_statement.py` `execute`, `build_rows`, `build_summary`, `statement_message` | Reusable with changes | The structure is sound: `resolve_company` first, then `show_ledger` and `show_wages` flags, and a `complete` flag per row. It has no card money level check, because it was written before FR-179 added `role_reads_money` to the supplier reports. Add that check. |
| `crusher_owner_statement/owner_statement_pdf.py` (POST endpoint, `frappe.has_permission(report.ref_doctype, "print")`, `resolve_company`) | Reusable with changes, last | It follows `equipment_supplier_statement/statement_pdf.py`. Build it after the statement is stable. |
| `card/company_scope.py` `SCOPED_DOCTYPES` and `card/hooks.py` `_COMPANY_SCOPED` additions | Reusable as is | Needed for each new company-scoped DocType (FR-131). |
| `card/tests/test_crusher_owner.py` (1,214 lines); `test_bola_matrix.py` PDF case | Reusable with changes | The cases for cross-company refusal, hidden ledger figures and hidden wages are the acceptance list for the later phases. |

## 2. Standard-first assessment

The question: which standard ERPNext mechanism can represent a partner's share before any CARD code?

| Need | Standard mechanism | Assessment |
|---|---|---|
| The partner as a party | **Supplier** | Works today. The partner machine names the Supplier in `Card Equipment.supplier`. Valid when the company owes the partner a payable. If the accountant treats the partner's balance as an owner current account instead, this option does not apply (decision D3). |
| The entitlement as a fixed rental of the machine | **Purchase Invoice** for the rental, built as a draft by CARD | Works today with no new code. Set the partner machine to the sub-rental direction with a supplier rate. `card/gl/posting.py` builds the draft Purchase Invoice for the partner and the draft Sales Invoice for the customer. A person submits both. |
| An advance to the partner | **Payment Entry** on the payment date (advance to a Supplier), then Payment Reconciliation | Standard ERPNext. CARD creates none. Behavior not verified against the installed ERPNext source. |
| A cost or a salary charged to the partner | A **Purchase Invoice return (debit note)** on the partner, or a **Journal Entry** with the Supplier party as an exception with a written reason | Standard ERPNext. The charge then is in the partner's ledger once. CARD creates none. Not verified against the installed ERPNext source. |
| Costs tagged to one machine | **Accounting Dimension** `Card Equipment` (`card/dimension.py` `ensure_card_equipment_dimension`) | Exists in the app. Off by default: `Card Settings.enable_card_equipment_dimension` (`dimension_switched_on`). When on, each ledger row can carry the machine. This is the exact way to read "costs of this machine". |
| Costs of a site or a job | **Cost Center** and **Project** | In use: `card/gl/posting.py` `card_cost_center`. A cost center often serves several machines, so it gives the cost of a machine only by an estimate. Use it as a fallback and label the figure "estimated". |
| The partner statement | **Equipment Supplier Statement** (CARD) and the standard **General Ledger** and **Accounts Payable** reports | For the fixed rental model these already show card net, invoices, payments and balance for the partner as a Supplier. |
| **Shareholder** | Not applicable | The Shareholder records of ERPNext describe shares in the company (not verified against the installed source). A partner owns a machine, not a share of the company. `SETTLEMENT-PARTY-DESIGN.md` section 1 states the same rule: no Shareholder record and no equity account follows from a family relation or from machine ownership. |

Conclusion:

```
STANDARD_OPTION_CHECKED=YES (CARD source on origin/main; installed ERPNext source NOT VERIFIED)
STANDARD_OPTION_USED=YES for the fixed rental model (Supplier + Purchase Invoice + Payment Entry + existing statement)
STANDARD_OPTION_USED=NO for the revenue-share model
REASON_FOR_CUSTOM=No standard ERPNext document computes "customer revenue of a machine minus the costs of that
  machine" for a third party. CARD can compute and show that figure. An accountant still books it with a standard
  document. CARD writes no ledger row.
```

## 3. Proposed design

### 3.1 Two entitlement models

| | Model A: fixed rental | Model B: revenue share |
|---|---|---|
| Agreement with the partner | A rate per hour, day or month | The customer revenue of the machine minus agreed deductions |
| Entitlement source | The supplier side of the submitted cards | The customer side of the submitted cards minus costs |
| ERPNext document | Purchase Invoice per month (exists) | A document the accountant books from the computed figure (decision D3) |
| New CARD code | None | The read-only statement of section 3.4 |

Model A is the default. Model B is used only for a machine whose agreement requires it. Field `owner_model` from
pull request 225 can carry this choice after decision D2. Its two values on the branch ("Managed partner",
"Self-operating owner") describe who operates the machine. The entitlement model is a different fact. Do not put
both meanings in one field.

### 3.2 Data (reuse first)

| Data | Where | New? |
|---|---|---|
| The machine belongs to a partner | `Card Equipment.ownership` = `طرف ثالث` | No |
| Who the partner is | `Card Equipment.supplier` (Supplier), copied to the card at creation (`Card Monthly Card.supplier`, kept as history per FR-171) | No, if decision D3 = Supplier |
| First month counted | `Card Equipment.owner_entitlement_from` (Date, permlevel 1, commercial field) | Yes, from pull request 225, model B only |
| Entitlement model | One Select on `Card Equipment` (permlevel 1, commercial field) | Yes, model B only |
| Costs of the machine | Ledger rows with the `card_equipment` dimension | No (the dimension must be on) |
| Charges to the partner, advances, payments | ERPNext documents on the partner's ledger | No |
| A share table for a machine with several partners | Child table on `Card Equipment` | Deferred (section 7) |

No new submittable DocType is needed for model A. For model B, the only new record with a clear case is the customer
approval of an addition row (`Card Owner Revenue Approval`), and only when such rows exist.

### 3.3 How the entitlement is computed

All figures are before VAT. Only submitted cards count. A month with a draft card is shown apart and is never in a
total (rule from `card/owner_statement.py` on the branch).

Model A, per partner and month:

1. Entitlement = sum of `Card Monthly Card.net_amount` of the partner's submitted cards (supplier side).
2. Charges and payments = the partner's ledger rows in ERPNext.
3. Balance = the ERPNext payable balance of the partner. CARD shows it and never stores it.

Model B, per partner machine and month:

1. Revenue = `Card Monthly Card.customer_net_amount` of the submitted cards of the machine.
2. Machine costs = expense ledger rows of the company tagged with the machine through the `card_equipment` dimension.
   Payroll accounts are excluded (see 3.5). Without the dimension, the figure is an estimate from the cost center and
   the statement labels it "estimated".
3. Charges to the partner = ledger rows on the partner's party (debit notes, Journal Entry lines, paid on behalf).
4. Computed entitlement = revenue minus machine costs. Charges and payments are shown below it. They are in the
   ledger already, so the statement subtracts them once, in the balance.
5. A cost that is tagged to the machine and is also charged to the partner in the ledger counts once. The statement
   lists such pairs as a warning for the accountant. It does not resolve them.

The computed entitlement of model B is information. It becomes a payable only when a person books a standard ERPNext
document for it. CARD never writes a ledger row (`card/tests/test_gl_neutrality.py` protects this rule on `main`).

VAT: the partner's entitlement carries input VAT only on a Purchase Invoice with a valid tax invoice from the
partner. The treatment for a partner who issues no invoice is an accountant question
(`SETTLEMENT-PARTY-DESIGN.md` A4). This design assumes nothing about it.

### 3.4 What the partner statement shows, and the gate of each figure

The statement runs for one company. `resolve_company(filters)` refuses a company the user cannot see. Each query
filters on that company. A machine, card or ledger row of a different company is never read.

| Figure | Source | Gate | Without the gate |
|---|---|---|---|
| Partner machines, partner name | `Card Equipment` (`ownership`, `supplier`) | Report role, plus read on permlevel 1 of `Card Equipment` | The statement is refused |
| Days, hours, card count | `Card Monthly Card` | Report role | — |
| Card amounts (entitlement of model A, revenue of model B) | `Card Monthly Card` money fields | Card money level: `role_reads_money()` | Columns and tiles are removed with `strip_money`. The values do not reach the browser. |
| Machine costs | `GL Entry` | Ledger gate `can_view_ledger(company)`, and read on permlevel 2 of `Card Equipment` (the cost fields of a machine are at level 2, `card/field_privacy.py`) | Removed with `strip_ledger`. The row is marked "incomplete". |
| Partner ledger: invoices, charges, advances, payments, balance | `GL Entry` (or `Payment Ledger Entry`) on the partner's party | Ledger gate | Removed with `strip_ledger`. Notice from `ledger_notice()`. |
| Computed entitlement of model B | Derived from card amounts and machine costs | Card money level and ledger gate, both | Not shown |
| Salaries | Not read by CARD | — | See 3.5 |

Rules for all figures:

- A figure is removed on the server. Hiding a column in the browser is not a gate.
- `frappe.get_all` applies no document permission. Each read therefore sits behind its gate in code, as in
  `equipment_supplier_statement.py` `execute`.
- No `ignore_permissions`, no new role, no change to a role of ERPNext.
- The report roles are a new grant on a new report. They need decision D6.
- No endpoint writes. A PDF endpoint, if built, uses POST and checks print permission and the company.

### 3.5 Salaries

CARD does not read `Salary Slip`, `Salary Structure Assignment` or any payroll record in this design.

The statement shows this instead:

- A salary the company charges to the partner is in the statement only when an accountant booked it on the partner's
  ledger in ERPNext. The statement shows that ledger line with its document number and amount, under the ledger gate.
- Machine costs exclude payroll expense accounts. On a machine with one operator, a payroll total per machine equals
  one person's salary. The exclusion prevents that leak. Reuse `excluded_expense_accounts` from the branch, without
  its read of `Salary Component Account` if HRMS is absent.
- The statement prints a fixed note: "Wages are not computed by CARD. Wages charged to the partner are shown only when
  they are booked on the partner's ledger."

If the owner later wants CARD to compute wages per machine, that is decision D4, with the `can_view_wages` gate of
pull request 225 as the minimum.

### 3.6 Switches

Each phase sits behind its own field in `Card Company Settings`, default off, read with
`card/settings.py` `company_setting(company, fieldname)`. One switch never turns on a later phase.

## 4. Smallest safe slice

One change: a **partner split in the Equipment Suppliers Summary**, behind a company setting that is off by default.

**Implemented as FR-190** on 2026-11-25 (in review). Differences from the table below:

- The filter value "Partner-owned only" was not built. The report JavaScript is unchanged.
- The summary also gets one tile, "Net cards (partner-owned)", under the same card money level check.
- The setting sits in its own collapsible section, "Partner-owned equipment".
- `test_settings_layout.py` and `test_settings_wiring.py` needed no change: they do not list the fields of
  `Card Company Settings`.
- The tests were written first and were not run on a site.

It answers the first owner request ("who owns each machine, and what do the cards say we owe each partner") with data
and gates that exist today. It reads no ledger row that the report does not read today. It reads no salary. It adds
no role, no DocType and no ERPNext document.

Precondition: decision D1 (met on 2026-11-25 for this slice). No other owner decision is needed, because the slice shows
only what `Card Equipment.supplier` ("Lessor / Owner") records today.

| Item | Detail |
|---|---|
| Setting | `Card Company Settings.partner_equipment_split`, Check, default `0`, permlevel 1 (as all fields of that table), label "Show partner-owned equipment in the suppliers summary" |
| When off | The report is identical to today: same columns, rows, tiles and message. An empty value and a company without a settings row count as off. |
| When on | `equipment_suppliers_summary.py` `execute` adds two columns per supplier row: `partner_equipment_count` (machines whose submitted cards in the period have `ownership` = `طرف ثالث`) and `partner_net` (the part of `net` from those cards). It adds one filter value "Partner-owned only". |
| Gates | `partner_equipment_count`: as `equipment_count` today. `partner_net`: card money level; add the key to the `strip_money` call in the same file. Company: the `resolve_company` call that exists. Ledger columns: not touched. |
| Accounting effect | None. Read-only. No posting code changes. |
| Permission effect | None. Same report roles (System Manager, Card Manager, Card User, Accounts Manager in `equipment_suppliers_summary.json`). The new setting is at permlevel 1 as the other fields of the table. |
| Files | `card/card/doctype/card_company_settings/card_company_settings.json` (one field); `card/card/report/equipment_suppliers_summary/equipment_suppliers_summary.py` and `.js`; `card/locale/main.pot` and `ar.po` (CARD strings only); `CHANGELOG.md`; `docs/governance/FEATURE-REGISTRY.md` (new FR number); website "What's new" (English and Arabic) and the generated reference pages |
| Tests | New `card/tests/test_partner_equipment_split.py`: (1) off = columns and rows equal to the baseline; (2) on = count and net are correct for a mix of rented and partner machines; (3) a user without the card money level gets no `partner_net` key in any row; (4) a user restricted to a second company gets a refusal for the first company; (5) company A on and company B off behave independently. Update `test_settings_layout.py` and `test_settings_wiring.py` for the new field. Run `test_report_access.py`, `test_card_money_privacy.py`, `test_baseline_regression.py`, `test_gl_neutrality.py`. |
| Migration | One new column in a child table, default 0. No patch. A second migrate changes nothing. |
| Rollback | Turn the setting off, or revert the commit. No data to restore. |
| Effort | About 1 working day of code and tests, plus review (`/code-review`, `/security-review` because a report gate changes) and one check on the existing QA site. |

Limits of the slice, stated for the owner:

- It shows card amounts, not an entitlement after deductions.
- It covers partner machines that name their partner today. A partner machine without a Supplier is not in the
  supplier reports (filter `supplier is set`), and the slice does not change that.

## 5. Open owner decisions

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Reopen issue 300? | (a) Reopen for the slice of section 4 only. (b) Keep deferred. | Decided 2026-11-25 for the slice (owner instruction, relayed). The label on the issue still says deferred: the owner updates it. |
| D2 | How is a partner paid? | (a) A fixed rental rate per machine. (b) The customer revenue of the machine minus costs. (c) Both, chosen per machine. | (a) as the rule: it works today with standard invoices. (c) only if a real agreement requires (b). |
| D3 | What is the partner in the books? | (a) A Supplier with a payable balance. (b) An owner current account without a party (assumptions A1 to A5 of `SETTLEMENT-PARTY-DESIGN.md`). | The accountant decides. (a) for a partner outside the company who receives payments. No code for (b) before the accountant confirms A1 to A5. |
| D4 | Salaries charged to a partner | (a) The accountant books the charge in ERPNext. CARD shows the booked line and reads no payroll. (b) CARD reads salary slips and computes wages per machine for users with full payroll access. | (a). |
| D5 | Tag costs per machine in the ledger (turn on the `Card Equipment` accounting dimension)? | (a) Yes, after a backup and a rehearsal on a test copy. (b) No, use cost centers and accept estimated figures. | (a). It is needed for model B and useful without it. It is a separate approved operation. |
| D6 | Who can open a partner statement (later phase)? | (a) System Manager, Card Manager, Accounts Manager. (b) Also Card User. | (a). |

## 6. Risks

| Risk | Effect | Control |
|---|---|---|
| A computed entitlement is read as a payable | A partner is paid from a CARD report and not from the ledger | The statement labels the figure "computed, not booked" and shows the ERPNext balance next to it. Payment stays a Payment Entry by a person. |
| Double count: a cost tagged to the machine and also charged to the partner | The partner is charged twice | The statement warns on such pairs (3.3 step 5). The accountant resolves them. |
| Salary leak through cost totals | One operator's pay is visible to a user without payroll access | Payroll accounts are excluded from machine costs (3.5). A test with one operator on one machine. |
| Cross-company read | A user sees a partner or a balance of a second company | `resolve_company` and a company filter on each query. Cross-company tests for each new read, as in `test_report_access.py`. |
| Partner as Supplier is the wrong model for some partners | Balances in the wrong account class | Decision D3 before any model B code. Model A changes no account. |
| The dimension is off | Machine costs are estimates | Label "estimated". Decision D5. |
| Supplier rate missing on a partner machine in the sub-rental direction | No Purchase Invoice line, so no entitlement in model A | `card_equipment.py` `validate_rental_direction` requires the supplier side for supplier-billing directions (the supplier is checked there; the rate rule was not read in full: not verified). |
| The closed branch is old | Conflicts and failing tests when code is copied | Extract small pieces on new branches from `main`. Do not merge or rebase the branch. |
| History changes when a partner changes | Old months move to the new partner | The card keeps the supplier it was created with (FR-171). Reports read the card's stored value. |

## 7. Out of scope

- Any ledger posting, payment or settlement by CARD for a partner.
- Reading payroll data in CARD.
- Shareholder records, equity accounts and owner current accounts (accountant, `SETTLEMENT-PARTY-DESIGN.md`).
- Several partners on one machine with shares.
- Family settlement groups (`settlement_family`).
- The rented-out direction for partner machines.
- `Card Owner Deduction` and `Card Owner Revenue Approval` DocTypes.
- The A4 PDF of a partner statement.
- A partner login or portal.
- Migration of existing production records and turning on the accounting dimension on any site.
- Merge, rebase or deletion of branch `feat/crusher-owner-statement`.
