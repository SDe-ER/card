# Authorization Rule on CARD-generated invoices (FR-159 companion note)

This note is **guidance**, not code. It explains how to add an **Authorization Rule** (ERPNext native)
on `Purchase Invoice` and `Sales Invoice` grand totals so that the CARD approval tier (FR-159, WP-E) is
complemented at the invoice side. CARD enforces the tier at the **source** (`Card Monthly Card.submit`);
Authorization Rule enforces a threshold at the **generated invoice** (ERPNext draft the accountant
submits). The two together close #35 G3 ("approval tiers per company, per DocType, per amount") without
any CARD-specific widening of roles or DocPerms.

The CARD app does not create these records. The owner configures them on Production once per company
after FR-159 ships and after Accounting on CARD is enabled (`enable_accounting = 1`, setup step W-14).
A clean site runs exactly as before while the rules are absent.

## 1. Where it fits in the closure plan

- Closure plan section C, WP-E: "FR-051 thresholds and server `approval_tier`; workflow condition;
  Authorization Rule note".
- Closure plan section E, W-17: "(after E) thresholds per company; ERPNext Authorization Rule on
  Purchase/Sales Invoice grand total".
- Owner decisions O-07 (CARD approval tiers Warn -> Refuse per company), W-15 (Card Reviewer role to
  named supervisors).

## 2. What Authorization Rule does (ERPNext native)

`Authorization Rule` (ERPNext module: Accounts) sets a per-company, per-doctype, per-transaction-value
threshold above which a named role, or a specific user, is required to submit. Standard reference:
<https://docs.frappe.io/erpnext/authorization-rule>. The rule does not widen a role; it refuses the
submit of a draft invoice above the threshold until a user holding the authoriser role submits it.

Supported transactions include `Purchase Invoice` and `Sales Invoice`, which is what CARD creates
(`card/gl/posting.py`). The rule reads `base_grand_total` of the invoice in company currency, so the
amount is directly comparable with the CARD approval tier (also company currency, O-17).

## 3. How it complements FR-159

| Layer | Who gates | Where enforced | What it checks |
|---|---|---|---|
| CARD approval tier (FR-159, this release) | `card/governance.py` `_check_approval_tier_role` | `before_submit` of `Card Monthly Card` on every route | Net amount of one card against the per-company `approval_tier_thresholds` on Card Company Settings |
| Authorization Rule (manual setup, owner) | ERPNext `authorization_rule.py` | `before_submit` of `Purchase Invoice` and `Sales Invoice` | Grand total of the monthly CARD draft invoice |

A single card is gated at submit (FR-159). The whole month's generated draft invoice, which can bundle
many cards for one party, is gated at the accountant's submit (Authorization Rule). The two thresholds
are independent: the owner sets each one from its own operational view.

## 4. Suggested setup (one company, one party type)

Settings for a Production configuration that mirrors the CARD approval tier for one example company:

- **Document Type**: `Purchase Invoice` (then repeat for `Sales Invoice`).
- **Company**: the owner's company (every row is per-company).
- **Based On**: `Grand Total`.
- **Transaction**: `Submit`.
- **Approving Role**: the role that should authorise above the threshold. Use one of the roles the
  owner already has (`Accounts Manager`, `Card Manager`, or a named `Card Reviewer`); never create a
  new role here.
- **Approving User**: leave empty for a role-wide rule, or name a specific user when the owner wants a
  single approver.
- **Based On Value**: the Saudi-Riyal threshold (company currency).
- Repeat for each threshold the owner wants on the invoice side (the Authorization Rule list supports
  more than one row per DocType and company; the highest matching row applies, same model as the CARD
  tier).

## 5. Keep the two in sync

Because FR-159's `approval_tier_thresholds` table and ERPNext's Authorization Rule are set in two
different places on Production, the owner:

- picks the same company currency (company default, O-17) on both;
- sets the Authorization Rule threshold **at or above** the matching CARD tier threshold, so a card
  that passes the CARD tier does not then fail the invoice rule for a reason the operator did not see;
- lists the CARD Approval Tier Threshold and the Authorization Rule for each company in the owner's
  Production setup log, under W-17.

A mismatch is not an error: it only means the accountant may have to escalate at the invoice side.
Neither rule changes the other's data.

## 6. What never changes

- CARD never writes GL entries. This rule applies at submit of the ERPNext invoice the accountant
  reviews, through the standard ERPNext ledger.
- No role, DocPerm or User Permission is added by this note or by FR-159. Every role named here must
  already exist on the site and already be granted by the owner through the Role Permission Manager.
- The rule is opt-in per company: a company with no Authorization Rule row behaves exactly as today,
  and a company with an empty CARD `approval_tier_thresholds` behaves exactly as today
  (`approval_tier = 0`, current behaviour unchanged).

## 7. Rollback

Removing Authorization Rule rows on Production restores the current ERPNext behaviour instantly; the
rule is a configuration record, not code. The CARD approval tier is unaffected by that removal; its
own rollback is "clear the `approval_tier_thresholds` rows on Card Company Settings" (per company).

## 8. References

- ERPNext Authorization Rule: <https://docs.frappe.io/erpnext/authorization-rule>.
- Frappe permission types: <https://docs.frappe.io/framework/permission-types>.
- Closure plan rows: section C "E", section E "W-17", section F "O-07".
- CARD governance: `card/governance.py` (FR-159 helpers), `card/governance_workflows.py` (FR-152
  Approve-transition condition with `user_holds_approval_tier_role`).
