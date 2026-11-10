# Accounting examples

Rule (`AGENTS.md`): **CARD never writes GL entries.** It creates, or links to, standard ERPNext documents through the
Document API; ERPNext posts the ledger when a person submits them. A search of `card/` (tests excluded) finds `GL Entry` only in reads
(reports, `get_meta` checks) and no `make_gl_entries` call. The only `frappe.new_doc` calls for financial or stock documents are:

| Created by CARD | Where | State it is left in | Who submits it |
|---|---|---|---|
| Purchase Invoice | `card/gl/posting.py` `build_monthly_posting` | Draft (`docstatus` 0) | An accountant, in ERPNext |
| Sales Invoice | the same function | Draft | An accountant |
| Material Request | `card/materials.py` `approve_review` | Draft | Buying or stock team |
| Stock Entry (Material Transfer) | `card/card/doctype/employee_tool_custody/employee_tool_custody.py` `_make_stock_entry` | Submitted in the same transaction as a confirmed Handover or Return, with the confirmer's own ERPNext rights | The confirmer |
| Stock Entry (Material Issue) for Loss or Damage | the same function | Draft | Stock team |
| Accounting Dimension "Card Equipment" | `card/dimension.py` | Created by an explicit manual command, never by migrate | Administrator |

CARD does **not** create: Journal Entry, Payment Entry, Purchase Order, Purchase Receipt, Credit Note, Asset Movement,
Timesheet or Expense Claim. It reads Payment Entry and Journal Entry only for reports (`card/report/card_settlement_status`).

Amounts below are illustrative. "Company A" has a company currency "CUR" and single-rate purchase and sales tax
templates. The VAT rate on a generated line comes from the per-company Item Tax Templates that
`gl/masters.py` provisions (section 0), which today are 15% for a taxable line and 0% for a non-taxable one; the examples
use 15% for that reason. Whether that is acceptable outside the current regime is risk R-07.

## 0. Masters CARD provisions before the first posting

`ensure_posting_masters` (`card/gl/masters.py`, called from the gated build; idempotent) creates standard ERPNext
masters through `insert(ignore_permissions=True)` and fills the blanks of the company's Card Company Settings row:

| Master | Created when | Content |
|---|---|---|
| Item Group "Card Services" and "Card Adjustments" | Missing | Containers for the items below |
| Item `CARD-RENTAL`, `CARD-DIESEL`, `CARD-TRANSPORT`, `CARD-RENTAL-OUT` | The matching item field of the company row is empty | Service items for the four kinds of invoice line |
| One Item per enabled adjustment type, named `CARD-ADJ-<TYPE>-<company abbreviation>` | The type has no item | Line item of a typed addition or deduction |
| Item Tax Template "CARD VAT 15% - <abbr>" and "CARD VAT 0% - <abbr>" | The company row has none and the company's VAT account heads can be read from the tax templates | Rates 15 and 0 on those heads. An existing template named in the row is re-pointed (heads and rates) to match |
| Price List "Standard Selling" (selling, enabled, company currency) | Only when Selling Settings has no default and no enabled selling list exists | A Sales Invoice needs a selling price list; the rates on the invoice are explicit and pricing rules are ignored |

The posting preview (`_masters_to_provision`) reports what the first posting would create without creating it. Where
the masters sit in the settings model: [03-source-of-truth-matrix.md](03-source-of-truth-matrix.md) section 3.

## 1. Supplier side: one draft Purchase Invoice per supplier per month

Preconditions checked before anything is created (`gl/preflight.py`, `gl/posting.py` `_plan_monthly_posting`):
accounting enabled in Card Settings; accounts, cost center and items set in the company row; the period is open; the
company has the "Card Equipment" accounting dimension (fail-closed); Buying Settings allow negative rates and repeated
items, and no Purchase Order is required; a VAT-registered supplier has a purchase tax template; no other active posting
exists for the same party-month-side; hand-booked invoices of the month that book to the same accounts or items are
reviewed by an accountant first.

Sources (all Submitted, not yet invoiced, same company, supplier and month):

| Source | Detail |
|---|---|
| Card Monthly Card EOMC-2026-10-0001, Equipment CEQ-0001 (rented in from Supplier X), Project P1 | 88 working hours, rate 600 per day of 10 hours = **5,280**; deduction "late arrival" 280 |
| Project Diesel Fill DSL-00001, same project and equipment | 500 L x 2.00 = **1,000**, price basis Exclusive |
| Equipment Transport TRN-00001, Company bears the cost, paid to Supplier X | **400**, one equipment share |

Draft Purchase Invoice created (company currency, rate 1, `update_stock` 0, posting date = last day of the month,
`disable_rounded_total` 1):

| Line | Item (from company row) | Account (expense) | Amount | Project | Cost center | Card Equipment dimension |
|---|---|---|---|---|---|---|
| Monthly operation card EOMC-... | `rental_item` | `equipment_rental_expense_account` | 5,280.00 | P1 | assignment, else project, else company default | CEQ-0001 |
| Deduction "late arrival" | the adjustment type's item | the adjustment type's account | -280.00 | P1 | same | CEQ-0001 |
| Diesel fill DSL-00001 | `diesel_item` | `diesel_expense_account` | 1,000.00 | P1 | the fill's own | CEQ-0001 |
| Equipment transport TRN-00001 | `transport_item` | `transport_expense_account` | 400.00 | P1 | resolved by the transport | CEQ-0001 |

Net total 6,400.00. The purchase tax adds 960.00 (15%). Grand total 7,360.00. Credit-to is the company's
`payable_account`. CARD also writes:

- one **GL Posting Log** (status Draft, `origin` Built, `posting_key` = company|Supplier|Supplier X|10|2026) with
  three kinds of **GL Posting Source** rows (card 5,000.00; fill 1,000.00; transport 400.00 - the card's net after the
  deduction, so the sources total equals the invoice net total);
- a signature of the built lines, checked again at submit.

What ERPNext posts when the accountant submits it (not written by CARD):

| Account | Debit | Credit |
|---|---|---|
| Equipment rental expense (net of the deduction line) | 5,000.00 | |
| Diesel expense | 1,000.00 | |
| Transport expense | 400.00 | |
| VAT input (tax template account head) | 960.00 | |
| Payable to Supplier X | | 7,360.00 |

On submit CARD writes the invoice link and `posted` on the card, fill and transport and sets the log to Submitted. The
accountant must also enter the supplier's Bill No and Bill Date if Supplier X holds a tax identifier (`gl/events.py`
`before_submit`).

**Inclusive diesel price.** If the company's `diesel_price_vat_basis` is Inclusive and the supplier is VAT-registered,
each fill line is booked net: a fill of 1,150.00 gross becomes 1,000.00 with 150.00 VAT, so VAT is not added twice
(`_apply_diesel_vat_basis`). If the basis is not set, the build is refused for review.

## 2. Customer side: one draft Sales Invoice per customer per month

Source: Card Monthly Card for Equipment CEQ-0002 (owned, rented out to Customer Y), customer amount **9,000.00**, with a
taxable customer deduction of **500.00**.

| Sales Invoice field | Value |
|---|---|
| Line | One item `rental_out_item`, rate 9,000.00, income account `equipment_rental_income_account`, project P1, dimension CEQ-0002 |
| Negative lines | **None.** The rule for the e-invoicing regime is built in: a taxable deduction becomes `discount_amount` 500.00 applied on Net Total |
| Net total after discount | 8,500.00 |
| Sales tax | 15% = 1,275.00 |
| Grand total | 9,775.00, debit-to `receivable_account` |

ERPNext posts: debit receivable 9,775.00; credit rental income 8,500.00; credit VAT output 1,275.00. A non-taxable
customer deduction is refused (it would shift the VAT base). A zero-rated line mixed with a deduction discount is
refused for the same reason. A customer-billing card needs the customer on the equipment before it can be submitted.

A sub-rental card bills **both** sides: it reserves the card on the supplier posting and on the customer posting
separately. The log's `party_type` decides which side a reservation belongs to.

## 3. Late source after the invoice is submitted

If a card is submitted after the month's invoice was submitted, the next build creates a supplementary posting
(`sequence` 2, key suffix `|2`) with only the new sources. If the primary posting is still a draft, the builder refuses
and asks for a rebuild: `rebuild_monthly_posting` deletes the draft, which frees its sources, and builds again.

## 4. Cancellation and correction

| Action | Effect |
|---|---|
| Cancel the Purchase Invoice or Sales Invoice (ERPNext reverses the ledger) | `before_cancel` clears the invoice link and `posted` on every source and sets the log to Cancelled; the sources can be posted again or amended |
| Delete a draft invoice | `on_trash` frees the sources and cancels the log |
| Cancel a card that is in an active posting | Refused: "cancel that invoice first" |
| Amend a card whose posting is still active | Refused (`_block_amended_copy`) |
| Edit lines or discount on a CARD-built draft | Refused for the discount; a value edit that no longer matches the sources fails at submit and must be rebuilt, unless an accountant accepts a correctable difference with a reason (`gl/integrity.accept_correction`) |
| Correct a submitted invoice | Use ERPNext return, credit note or debit note. A return or debit note is not blocked by the CARD copy check (`before_submit`) |

Where an invoice has already been cleared by an e-invoicing authority, the correction is a credit note, not a cancel
(the owner's accounting practice). CARD does not create the credit note.

## 5. Supplier accrual already booked by hand

Some supplier cards were recognised by a Journal Entry before CARD invoiced them. `link_accrual_journal`
(`card/gl/journal_link.py`, accountant roles only, POST) records that link without creating or changing anything in
ERPNext:

| Example | Value |
|---|---|
| Existing Journal Entry JV-0001 | Debit equipment expense 5,000.00, credit Supplier X payable 5,000.00 (made by hand) |
| Cards linked | EOMC-2026-10-0001 (net 5,000.00) |
| CARD writes | One GL Posting Log, `origin` Linked, `posting_type` Journal Entry, listing the card |
| Evidence required | The JE credits exactly one supplier, and its credit equals the cards' net within `reconciliation_tolerance`; a gap needs an accountant's reason and is stored as an open difference |
| Effect | The monthly build skips the card, so it is not invoiced twice. Cancelling JV-0001 frees the card |

A hand-booked **supplier invoice** can be linked the same way (`gl/integrity.link_supplier_invoice`, `origin` Linked).

## 6. Documents CARD records a decision for but does not create

| Case | What exists | What does not (Planned) |
|---|---|---|
| Transport whose cost the customer bears: "Bill customer" decision | Decision, customer, amount, authorization fields on the transport (`record_financial_decision`) | The customer invoice. Billing, supplier recovery and absorption postings are disabled until the accountant and the tax adviser decide (code comment and `transport_accounting_review` report). Issue #49, #41 |
| Transport whose cost the equipment supplier bears: "Recover" | Recovery mode and amount | A deduction or adjustment document |
| A transport with a responsibility scenario | It is excluded from the monthly Purchase Invoice | Its own posting |
| Payment of invoices | Nothing. Payment Entry is entered in ERPNext | The company row has `mode_of_payment` and `bank_cash_account` fields, but no code path reads them |
| Diesel as a stock item with tanks | Nothing: a fill is an expense line | Diesel Issue bridge (FR-034, #47) |
| Depreciation | The Asset carries the Card Equipment dimension, so depreciation entries made by ERPNext land on the machine | Nothing created by CARD |

## 7. Stock and parts

| Step | Document | Ledger effect |
|---|---|---|
| Review approved, part from store | Draft Material Request, type Material Issue, with item, project, cost center, warehouse, dimension | None until the stock team acts |
| Review approved, part to buy | Draft Material Request, type Purchase | None. The Purchase Order, Receipt and Invoice buttons are Planned (FR-028) |
| Tool handed to a worker (confirmed) | Submitted Stock Entry, Material Transfer, store warehouse to the company's tool custody warehouse | Stock ledger moves in the same transaction as the custody record |
| Tool returned (confirmed) | Submitted Stock Entry, Material Transfer back | Same |
| Tool lost or damaged | Draft Stock Entry, Material Issue from the custody warehouse, with project, cost center and dimension | None until the stock team submits it. Any accounting follows ERPNext's stock settings for the company, not CARD |

## 8. Checks that protect the ledger

| Check | Source |
|---|---|
| One active posting per company, party, month and side, enforced by a unique database key on the log | `gl_posting_log.py` `posting_key` |
| Sources total equals invoice net total within tolerance, at build and again at submit | `gl/posting.py` `_assert_identity`, `gl/events.py` `before_submit` |
| Invoice posting date inside its unit's month, period open | `gl/events.py`, `gl/preflight.py` `check_period_open` |
| Sources locked while a build runs, then membership re-checked | `gl/integrity.lock_sources` |
| Duplicate supplier bill number refused | `gl/events.py` `_check_bill_no_unique` |
| An invoice CARD did not build may not repeat a CARD posting | `gl/integrity.check_not_a_copy` |
| The build uses `insert(ignore_permissions=True)`, so authorization is checked first: Card Manager or System Manager, and the company must be within the caller's scope for the source and written DocTypes | `gl/posting.py` `_checked_endpoint_args`. See risk R-06 |
