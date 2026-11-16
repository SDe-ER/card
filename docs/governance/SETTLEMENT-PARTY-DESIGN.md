# Settlement parties and ownership accounting (design, FR-170 follow-up)

Status: design. No posting is implemented from this document. Date: 2026-11-17.

## 1. Audit of the current code (main at b31c255, plus the FR-169/FR-170 branch)

| Area | What the code does | Evidence |
|---|---|---|
| Ownership | Three values: `ملك` (owned), `إيجار` (rented), `طرف ثالث` (managed for another owner) | `card/card/doctype/card_equipment/card_equipment.json` field `ownership`; `card/constants.py` |
| Rental direction | `مستأجَرة من مورد` (rented in, supplier Purchase Invoice), `مؤجَّرة لعميل` (rented out, customer Sales Invoice), `إيجار من الباطن` (both), `تشغيل داخلي` (internal, no billing) | `card/constants.py` lines 9-14 |
| Owner identity | Field `supplier`, labelled "Lessor / Owner", permlevel 1, shown only for rented-in or sub-rental equipment. It is a Supplier link. | `card_equipment.json` |
| Third-party equipment | Treated as internal (`INTERNAL_OWNERSHIPS`): internal operating rate, may link an Asset, never a rented machine. No owner entitlement and no owner payable on main. | `card/constants.py` line 6; `card/card_value.py` line 46 |
| Partner / joint ownership | None: no ownership share, no partner, no partnership party. | searched all `card/**/*.py` and DocTypes |
| Owner entitlement, owner deductions, owner statement | Designed in PR #225 (open, stale, DIRTY). Not on main. | `gh pr view 225` |
| Customer billing | Customer Sales Invoice per card for rented-out and sub-rental cards; additions and deductions on the customer side; non-taxable deductions become a credit note. | `card/gl/posting.py` (customer lines); FR-156 |
| Supplier billing | Supplier Purchase Invoice per card for rented-in and sub-rental cards. | `card/gl/posting.py` |
| Cost centers | Derived from the equipment's project assignments that cover the card's worked days. | `card/gl/posting.py` `card_cost_center` |

Conclusion: CARD on main bills the customer and the rental supplier correctly. It does not record who beneficially owns the operating surplus of a third-party machine, a partner's share, or a joint ownership. The owner-distribution model exists only as an unmerged design (PR #225).

## 2. Settlement party concept

A **Settlement Party** is the person or entity that is financially entitled to, or bears, a card's operating amount. It is not the same as the ERPNext Supplier, and it is not the same as the equipment ownership value.

Each equipment operating period records:

- `ownership`: company-owned, rented, or third-party (existing values);
- `settlement_party_type`: `Company`, `Supplier`, `Shareholder` (individual partner), `Partnership` (joint), `Other contracted party`;
- `settlement_party`: the ERPNext record (Company, Supplier, Shareholder) or a CARD record for a joint or contracted party;
- `share_pct`: ownership share; the shares must sum to 100% per equipment and period;
- `effective_from` and `effective_to`: the period the allocation applies to. History is never overwritten.

Each card carries a snapshot of the allocation that applied on its worked days, so a later change never alters a submitted card.

## 3. Transaction and accounting matrix

Legend: **Recognition** is the economic event that creates a receivable, payable, revenue or cost. **Payment** is the cash event. **Reconciliation** matches an existing balance; it never recognises anything new.

| Settlement party type | Ownership | Recognition on the customer side | Recognition on the party side | Cash paid by Shams Dubai on the party's behalf | Accounting party and account (ERPNext) |
|---|---|---|---|---|---|
| Company (own equipment, internal) | ملك | none (internal) | cost-centre cost only; no payable | Cash to expense; no party | Expense on the project cost centre; no Supplier, no Shareholder |
| Company (own equipment, rented out) | ملك | Sales Invoice (existing) | none | Cash to expense on the project | Income account on the Sales Invoice; no owner payable |
| External rental supplier (rented in) | إيجار | none | Purchase Invoice (existing) | Dr Supplier payable (Party Type Supplier), Cr cash | Party Type Supplier; the approved design |
| External rental supplier (sub-rental) | إيجار من الباطن | Sales Invoice (existing) | Purchase Invoice (existing) | Dr Supplier payable, Cr cash | Party Type Supplier |
| Individual partner (brother) | طرف ثالث | none on the card | owner entitlement = operating amount x share, recorded as a partner current account | Dr partner current account, Cr cash. Party Type Shareholder if the person is registered as a shareholder; otherwise a partner current account agreed with the accountant | Recommended default: Shareholder party and a partner current account (equity or liability). **To confirm with the accountant.** |
| Joint partnership | طرف ثالث | none on the card | operating amount x share for each partner, from one card-level recognition; shares sum to 100% | as above, per partner, or one Partnership record if the partnership is a legal party | One recognition, allocated proportionally; no duplicate lines |
| Other contracted party (invoices us) | any | depends on their invoice | Purchase Invoice from their Supplier record | Dr their Supplier payable | Party Type Supplier |
| Other contracted party (no invoice) | any | none | recorded as a CARD settlement entry, not invoiced | **Blocked until the accountant names the account and the party** | no default |

## 4. Rules that follow from the matrix

1. A card does not require `card.supplier` unless its settlement party is a Supplier. The `supplier` field stays as the rental supplier only.
2. A cash disbursement debits the recoverable balance of the settlement party (Supplier payable, partner current account, or partnership account). It never debits Supplier payable by default.
3. Each economic event has one accounting effect. A recognition creates the balance once; a payment only settles it; a reconciliation only allocates an existing balance.
4. The shares must sum to 100% per equipment and period, and the allocation is snapshotted on the card.
5. Customer VAT, supplier input VAT, partner distributions and statutory accounting stay in separate accounts. The distribution is calculated on the agreed pre-VAT operating amount.
6. A period that is closed or approved is never recalculated. Late changes become new entries.

## 5. Open items for the accountant (these do not block the design)

- Partner current account: the account type and party for an individual brother who is not a registered shareholder.
- Joint partnership: one party record for the partnership, or per-partner allocation.
- Other contracted parties without an invoice: the account and the party type.

## 6. Relation to other work

- PR #225 (FR-150, owners and the Crusher Owner Statement) is the closest existing design. It is stale and DIRTY. This document supersedes it for the accounting model, but not for its statement report.
- FR-170 step 1 (cash row validation) stays valid. Step 2 must use the settlement-party model above instead of assuming `card.supplier`.
