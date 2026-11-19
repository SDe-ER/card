# Settlement architecture: evidence, proposal and assumptions

Status: audit and design. No DocType, posting or migration is authorised from this document.
Evidence date: 2026-11-17. The ERP inspection was read-only (no account, party or document was created or changed).

Three kinds of statement are separated below:

- **Verified** — observed in the code on `origin/main` (b31c255) or in the live ERP (read-only), with the source named.
- **Proposed** — a design choice, not yet built.
- **Assumption** — an accounting or legal point that needs the accountant's confirmation before posting.

## 1. Verified: the distinctions the owner requires

These are separate concepts. Not one of them implies another.

| Concept | Meaning | Where it lives today |
|---|---|---|
| Legal company ownership | Who owns Shams Dubai (shareholders) | Not in CARD. ERPNext Shareholder records are not used by CARD. |
| Equipment ownership | Who owns the machine (ملك, إيجار, طرف ثالث) | `Card Equipment.ownership` |
| Financial beneficiary | Who is entitled to the operating amount | **Not recorded.** Only the owner's Supplier link exists (below). |
| Equipment partnership | Several people owning one machine together | **Not recorded.** No share, no partner, no partnership party. |
| External rental supplier | A Supplier who rents a machine to us | `Card Equipment.supplier` (label "Lessor / Owner") and the card's Purchase Invoice |

A brother of the owner, or an individual who owns equipment operated by Shams Dubai, is **not** a legal shareholder by that fact alone. No Shareholder record and no equity account is created from a family relationship.

## 2. Verified: current code (origin/main, b31c255)

| Area | Behaviour | Source |
|---|---|---|
| Ownership values | `ملك` (owned), `إيجار` (rented), `طرف ثالث` (managed for another owner) | `card/constants.py` line 5-6; `card_equipment.json` `ownership` |
| Rental directions | `مستأجَرة من مورد` (rented in: supplier Purchase Invoice), `مؤجَّرة لعميل` (rented out: customer Sales Invoice), `إيجار من الباطن` (both), `تشغيل داخلي` (internal, no billing) | `card/constants.py` lines 9-14 |
| Owner identity | `supplier` on the equipment, label "Lessor / Owner", a Supplier link, permlevel 1, shown only for rented-in and sub-rental equipment | `card_equipment.json` |
| Third-party equipment | Internal operating rate; not a rental; no owner entitlement, no owner payable | `constants.py` line 6; `card_value.py` `INTERNAL_OWNERSHIPS` |
| Customer billing | One customer Sales Invoice per card for rented-out and sub-rental cards; customer additions and deductions on that invoice; non-taxable deductions as a credit note (FR-156) | `card/gl/posting.py` |
| Supplier billing | One supplier Purchase Invoice per card for rented-in and sub-rental cards | `card/gl/posting.py` |
| Cost centre | Taken from the equipment's project assignment covering the card's worked days | `card/gl/posting.py` `card_cost_center` |
| Cash rows (FR-170 step 1) | A flagged owner-paid cash row is validated on save, excluded from totals and statements, and blocks submission | `card/adjustments.py`, `card_monthly_card.py`, commit `5ac5a0e` |

## 3. Verified: the live chart of accounts (read-only, 2026-11-17)

Company: مؤسسة شمس دبي للمقاولات. Installed ERPNext Party Types: **Customer (Receivable), Employee (Payable), Shareholder (Payable), Supplier (Payable)**.

The company already has an Equity group for partner and owner current accounts, **3500 - حسابات جاري المالك** (group, Equity). Its children:

| Account | Name | Enabled | GL entries | Observed use |
|---|---|---|---|---|
| 3520 | جاري المالك - سالم الدوسري | yes | **479** | All sampled entries are Journal Entries with **no party** (party type empty), costs on the head-office cost centres |
| 3525 | جاري المالك سالم - عمليات اكسبو الداخلية | yes | not counted | — |
| 3510 | جاري شراكة كسارات (ناصر + بداح) - CR-6 وCR-7 | **disabled** | **0** | Never used |
| 3530 | جاري الشريك فيصل | disabled | not counted | — |
| 3540 | جاري الشريك ناصر (أخو المالك) - CR-6 جلفان | disabled | 4 | Historical |
| 3545 | جاري الشريك والد ناصر الدوسري | disabled | not counted | — |
| 3550 | جاري الشريك بداح | disabled | not counted | — |
| 3560 | جاري الشريك محمد | disabled | not counted | — |

Verified facts from this table:

1. The company's current practice for owner and partner balances is **Equity accounts with no ERPNext party**, posted by manual Journal Entry. The live Shareholder party type is not used on these accounts.
2. The partnership account **3510** (ناصر + بداح, for the two crushers CR-6 and CR-7) exists but has never been posted to and is disabled. The partnership structure is therefore represented in the chart but not in use.
3. Individual partner accounts 3530, 3540, 3550 and 3560 exist, are disabled, and have little or no use.
4. Owner account 3520 is the only heavily used current account.

## 4. Verified: PR #225 (open, DIRTY, +4832, 36 files)

| Part of #225 | What it does | Reuse? |
|---|---|---|
| `Card Owner Deduction` (submittable) | Records a shared expense paid on behalf, with lines linked to a submitted source | **Reuse the idea**: it is the same event as a cash row. It must be re-based on the beneficiary, not on `supplier`. |
| `Card Owner Revenue Approval` | Customer approval of one customer-side addition row (Pending/Approved/Partially approved/Rejected), with a date and private evidence; outside the card | **Reuse the idea** for customer-side approval. Independent of beneficiary. |
| `Crusher Owner Statement` report | Per-owner statement of entitlements and deductions | **Reuse the report** after the beneficiary model is fixed. |
| `owner_entitlement_from`, owner model (managed partner / self-operating) on the equipment | First card month counted; owner model | **Reuse the field pattern**, not the Supplier link. |
| Owner = Supplier (`supplier` indexed as an owner filter) | Treats every owner as a Supplier | **Do not reuse.** This is the assumption the owner has corrected. |

#225 is too large to merge (36 files, +4832). The reusable parts should be extracted as small, separately reviewed changes.

## 5. Proposed: minimal architecture (no new DocType yet)

The owner asked to keep the model simple. The proposal is to extend what exists before adding anything new.

1. **Keep `card.supplier` and the equipment `supplier` field as the rental supplier only.** They are not the beneficiary for any other ownership type.
2. **Add one optional beneficiary reference on the equipment**, for the non-supplier cases only:
   - `beneficiary_type`: `Supplier` | `Account` (an existing Equity current account) | blank;
   - `beneficiary_account`: a Link to an existing enabled Equity account (for example 3520 or 3510).
   No new DocType. The reference is read at submit and copied onto the card, so an approved card keeps the beneficiary it had.
3. **Ownership shares only where needed.** A single beneficiary (one partner, one partnership account) needs no share table. A joint machine with individual allocation needs a share table; that is the only case where a new child table is justified. It is deferred until the accountant confirms the rules (section 7).
4. **Settlement against cash** uses the existing Journal Entry route (approved in FR-170) and Payment Reconciliation for supplier balances. No parallel ledger.
5. **Preserve history:** the card stores the beneficiary, and the entitlement amount, at submit. A later change to the equipment does not alter a submitted card.

## 6. Accounting matrix

Columns: **Beneficiary** · **Account** · **ERPNext Party Type** · **Source document** · **Dr / Cr** · **VAT** · **Reconciliation** · **Duplicate-posting protection**.

Status: **Verified** = the chart or code shows it. **Assumption** = needs the accountant (section 7).

| # | Case | Beneficiary | Account | Party type | Source document | Dr / Cr | VAT | Reconciliation | Duplicate protection | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Company-owned equipment | Company | Income on the customer Sales Invoice; cost on the project cost centre | Customer (on the invoice only) | Customer Sales Invoice (existing); no beneficiary document | Dr customer, Cr income (existing) | Output VAT on the taxable invoice lines (existing) | Sales Invoice vs Payment Entry (ERPNext standard) | One Sales Invoice per card (existing `purchase_invoice`/`sales_invoice` links) | **Verified** (code) |
| 2 | Equipment owned by an individual (brother), operated and billed by the company | The individual | The individual's existing Equity current account (for example 3530/3540); the operating cost on the project cost centre | None (existing practice: no party) | Approved monthly card → entitlement Journal Entry (new, FR-170 route) | Dr operating cost (share of the card amount, pre-VAT), Cr partner current account | **Assumption**: no VAT on the entitlement if it is not invoiced by the individual | Payment from cash: Dr partner current account, Cr cash; or offset against an open entitlement | One entitlement entry per card and beneficiary; the key is the card name plus beneficiary | **Assumption** (account type and direction) |
| 3 | Jointly owned equipment, one partnership settlement account | The partnership, through account 3510 | 3510 (exists, disabled) | None | Approved card → entitlement Journal Entry | Dr operating cost, Cr 3510 | Assumption as in 2 | Payment to the partnership: Dr 3510, Cr cash; the split between the partners is outside CARD | One entry per card; no second entry for the partners | **Verified** account exists and is unused; **Assumption** on use |
| 4 | Jointly owned equipment, individual allocation | Each partner | Each partner's current account, the amount = card pre-VAT amount × that partner's share | None | Approved card → one entitlement entry with one line per partner | Dr operating cost (total), Cr each partner account (its share) | Assumption as in 2 | As in 2, per partner | Shares must total 100% (validated before the card is approved); one card, one recognition | **Assumption** (share rules; needs the share table only here) |
| 5 | External rented equipment | Rental supplier | The supplier's payable (existing) | Supplier | Supplier Purchase Invoice (existing); Payment Entry | Dr expense, Cr supplier payable (existing) | Input VAT on the Purchase Invoice (existing) | Payment Entry vs Purchase Invoice (ERPNext standard) | `card.purchase_invoice` guard (existing) | **Verified** (code) |
| 6 | Customer-side additions and deductions | Company (customer relationship) | Customer income line on the Sales Invoice; credit note for non-taxable deductions (existing, FR-156) | Customer | Customer Sales Invoice or credit note (existing) | Existing logic, unchanged | Taxable deductions reduce the VAT base (existing) | Sales Invoice vs Payment Entry, credit note allocation (ERPNext standard) | Existing FR-156 logic; no beneficiary line is added to the customer's invoice | **Verified** (code) |
| 7 | Cash paid by Shams Dubai on behalf of a beneficiary | The beneficiary (cases 2–4) or the supplier (case 5) | Supplier: payable (Dr); partner: current account (Dr or Cr, per the accountant); cash account 1110 or 1120 (Cr) | Supplier for case 5; none for 2–4 | One Journal Entry at the approved payment date (FR-170 Step 2) | Dr beneficiary's recoverable balance, Cr the selected cash account | No VAT on the cash payment itself; the supplier's VAT is on its own invoice | The beneficiary balance is settled against later entitlements or invoices | One Journal Entry per approved payment (the approval holds the identity); cancellation of the payment does not cancel the card | Supplier case **Verified** (approved design); partner case **Assumption** |
| 8 | Settlement of entitlements against cash already posted | The beneficiary | The partner current account, or the supplier payable | Supplier for case 5; none for 2–4 | Payment Reconciliation (supplier) or a Journal Entry (partner) | Allocates an existing balance; **no new expense, no new payable** | None | Reconciliation document, linked to both sides | Reconciliation rows are unique per pair of documents; the allocation cannot exceed the open balance | Supplier **Verified** (ERPNext standard); partner **Assumption** |

Rules that follow from the matrix:

1. Customer revenue is recorded once, on the customer's Sales Invoice (case 1 and 6). An internal beneficiary allocation is an expense of the company, not a second revenue line.
2. A card's entitlement is calculated on the agreed **pre-VAT** operating amount. Customer VAT, supplier input VAT and partner distributions stay in separate accounts.
3. No automatic Shareholder record and no equity account are created from a family relationship. A partner account is used only where the chart already has one, and the accountant confirms it.
4. A closed or approved period is not recalculated. A later correction is a new entry.

## 7. Assumptions requiring validation (accountant)

These do not block the architecture. They block posting for the marked case.

| # | Question | Affects | Why it is open |
|---|---|---|---|
| A1 | Is an Equity current account (3520 / 3530 / 3540 …) the correct treatment for an individual brother's share of an operated machine, or is it a payable, an expense-sharing liability, or something else? | cases 2, 7 | The chart already uses current accounts for partners, but the legal relationship is not stated in CARD. The owner asked not to infer equity from family. |
| A2 | Is the direction of a cash payment on behalf of a partner Dr current account or Dr a receivable from the partner? | case 7 | Depends on A1. |
| A3 | Should the disabled partnership account 3510 be enabled, and is one partnership account enough, or is per-partner allocation needed? | cases 3, 4 | 3510 has never been used; the structure is not confirmed. |
| A4 | VAT on a partner entitlement that is not invoiced by the individual: none, or a reverse-charge or self-billing case? | cases 2–4, 7 | Not verified. |
| A5 | Is the entitlement calculated on the agreed pre-VAT operating amount for all beneficiary types, including the supplier case? | all | The owner states it; the accountant confirms the VAT base. |

## 8. Relation to other work

- FR-170 step 1 (cash row validation) remains valid. Step 2 uses the beneficiary model in section 5, not `card.supplier`, for non-supplier beneficiaries.
- PR #225 is a design source, not a merge candidate. Its reusable parts are extracted one at a time (section 4).
- No migration is authorised by this document. The first step after the accountant confirms A1–A5 is a read-only check of the equipment rows that would receive a beneficiary.
