# Downtime charges and minimum guarantees — assessment and rules

**Status: In review (FR-134, issue #45, conflict C-07, owner decision O-03).** This file is the "minimum-guarantee
assessment before implementation" that #45 asks for, and it records the rules CARD enforces for any charge for
stopped equipment. It changes no Production data. Nothing here is LIVE until the release that carries FR-134 is
deployed and checked in real use.

## 1. Owner rule (#45)

- Stopped equipment earns **no rental automatically**.
- A charge for downtime is an **explicit, approved manual addition** with a reason, a responsible party, an
  agreement reference and an audit trail.
- A minimum-guarantee clause in a contract must be assessed before anything is built; the owner rule is never
  overridden silently.

## 2. What existed before FR-134

| Mechanism | Since | Behaviour | Conflict with the owner rule |
|---|---|---|---|
| Fixed day statuses (عمل, إجازة, عطل, توقف من العميل) | v1 | Only عمل days bill operating hours; the other statuses bill nothing | None |
| Card Stop Reason `billable` (FR-118) | v4.6.0 | Off by default. When a Card Manager ticks it, every stopped hour with that reason is billed like an operating hour **on both sides** of the card | C-07: one tick bills every later stopped hour of the reason, with no recorded approval, no agreement reference and no choice of side |
| Card Equipment `min_hours` (FR-020) | v1 | Hidden field; **no code reads it** | None today, but it suggests a minimum guarantee that does not exist |
| Card additions/deductions (typed rows, S3) | v4.0.0 | Manual amount per side with a configured type and account | None, but nothing marked a row as a downtime charge or asked for its basis |

## 3. Minimum-guarantee assessment

A minimum guarantee ("the lessee pays at least N hours a month") is a contractual clause, not an operating fact.
Building it into the card calculation would:

1. bill hours that were never worked or recorded as stopped, which is the automatic charge #45 forbids;
2. need a per-contract rule (hours, period, which days count, what happens when the equipment moves project in the
   month, pro rata on partial months, which side), which CARD does not model: rates live on Card Equipment and the
   dated rate agreements are still a planned item (CHANGELOG, "Planned");
3. interact with the shift-limit warning, the billable stop reasons and the partial-month assignment periods in
   ways that are hard to audit after submit.

**Decision (O-03 default, recommended in the close-all plan):** CARD does **not** implement a minimum guarantee.
When a contract has one, the shortfall is charged with a **downtime charge** addition (section 4.2) that names the
contract clause in `agreement_reference`. FR-020 `min_hours` is retired: hidden, read only, labelled
"Deprecated – not used"; the column and any stored value stay, and no code reads it.

A future minimum-guarantee feature needs its own owner decision, its own FR number, and a design that keeps the
charge explicit (for example a proposed addition the reviewer approves), never a silent change of the card amount.

## 4. Rules CARD enforces (FR-134)

### 4.1 Billable stop reasons stay possible, but are audited and sided

- `billable` stays off by default (FR-118 default unchanged). O-03: SDCE keeps every reason non-billable.
- A billable reason must have `billable_approval_reason` (who approved it, under which agreement). Saving a billable
  reason without it is refused.
- `billable_side` is Supplier, Customer or Both (default Both). Existing reasons get Both (patch
  `v4_8_0.stop_reason_billable_side`), which is exactly the merged FR-118 behaviour.
- A card bills a billable reason's stopped hours only on its side. On a card that does not bill that side
  (for example a Customer reason on a rented-in card) the day row's `reason_billable` is 0, so every report,
  statement and summary that reads it stays consistent.
- On a sub-rental card (bills both sides) a one-sided reason is billed on its side's amount only; the card's
  `billable_stopped_hours` (shown on statements and summaries) still counts it, and a review warning says so.
- Card Stop Reason has `track_changes` on: every change of `billable`, side or approval is in its Version history.

### 4.2 Downtime charge addition (the recommended route)

- Card Settings → Addition/Deduction Types: a type flagged `is_downtime_charge` (off by default).
- A card row of such a type must name:
  - `stop_reason`: an enabled Card Stop Reason of the card's company (another company's reason is refused with a
    permission error);
  - `responsible_party_type` and the party (the record for Supplier/Customer, the card's company for Company, a name
    for Other);
  - `agreement_reference`: the contract clause, letter or approval that allows the charge.
- The row is an ordinary addition or deduction on its side: same account, tax and posting rules as any typed row.
- If the same card also bills that stop reason through `billable` on its days, the card warns that the downtime may
  be charged twice (review only, not blocked).
- Audit: Card Monthly Card has `track_changes` on, so the row and every edit of it are in the card's Version history;
  the card's review and submit flow is the approval.

## 5. Defaults and rollback

- Defaults: no reason is billable, no type is a downtime charge, every existing reason bills Both. Cards, amounts
  and postings of existing data are unchanged.
- Rollback: reverting the code leaves the new columns (`billable_side`, `billable_approval_reason`,
  `is_downtime_charge`, the downtime fields on adjustment rows) in the database, unused. A one-sided reason would
  bill both sides again after a rollback; check `billable_side` before rolling back if any reason is billable.

## 6. Open owner question

- O-03 confirmation: SDCE keeps every stop reason non-billable and charges downtime only through the downtime-charge
  addition (recommended: yes). Production setup W-6 checks that no reason is billable.
