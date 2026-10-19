# CARD Feature Registry

The permanent record of CARD features and fixes: what exists, where it lives, how it is proven, and what is still
open. It exists so that no working feature is lost silently during a rebuild or refactor.

## Rules

- **Update after every task.** Every task that adds, changes, fixes or removes a feature updates this file in the same
  task. If the file cannot be updated in that task (for example while this file waits for its own pull request),
  the task's checkpoint records the exact change to apply later.
- **Check before closing a task.** Compare the affected features with the current code on `main`, confirm that no
  earlier feature was lost, and record the evidence (PR, commit, file, tests). A task is not closed until this file is
  updated, or the reason it could not be updated is written down.
- **Stable IDs.** An ID (`FR-NNN`) is never reused, renumbered or reassigned. New features get the next free number.
- **No deletion.** A row is never deleted. A feature that is taken out gets the status **Removed**, with the reason
  and its replacement. A feature that was removed earlier and comes back keeps its old ID.
- **Verified against code.** A row says Implemented only when the code is on `main` and covered by tests; the
  Evidence column names the file or test. Planned work stays **Planned**.
- **Visual checks are separate.** A passing unit test is not a browser or device check; record those separately.
- Rows are added gradually, area by area, each one checked against the code at the time it is added.

## Status values

| Status | Meaning |
|---|---|
| Implemented | Merged to `main`, covered by tests |
| In review | Open pull request, not merged |
| Planned | Approved, design or code not finished |
| Implemented, not visible | Code exists but users have no entry point |
| Broken | Confirmed defect in `main` |
| Removed | Existed before, intentionally taken out (state the reason and the replacement) |

## Registry

Checked against `main` @ `dc57259` (2026-10-19).

| ID | Feature | Layer | Status | Evidence | Open points |
|---|---|---|---|---|---|
| FR-001 | Diesel fill form works for Card User: the supplier lock comes from the server (`get_supplier_editable`, yes/no only); Card Settings stays closed to fill users | Desk + Backend | Implemented | PR #77, merge commit `dc57259`; `card/card/doctype/project_diesel_fill/project_diesel_fill.py`; `card/tests/test_settings_wiring.py` TestDieselSupplierPolicy (6 tests); CI on PR #77: 8/8 checks pass (490 tests OK, 20 skipped), 0 code-scanning alerts; CI on `main` @ `dc57259`: CI + CodeQL pass (490 tests OK, 20 skipped), 0 open alerts | Browser check of the form not done |
| FR-002 | Diesel price lock: price per company from Card Company Settings, filled automatically, not editable by Card User; no new fill saved with a zero or missing price unless an authorised exception applies; exception for a role set in Card Settings (default Accounts Manager) with mandatory reason, user, original and new value, server-side audit; historical and approved fills never repriced; old drafts never change price silently | Backend + Desk | Planned | Owner decisions 2026-10-19 (Q1–Q4). Design under review; no code yet | Final design; implementation; tests; browser check |
| FR-003 | Default diesel price per company: `Card Company Settings.diesel_unit_price` is copied into a fill only when its price is blank; any user who can edit the fill may type another price | Backend | Implemented | `project_diesel_fill.py` `validate` | To be replaced by FR-002 |
| FR-004 | Monthly draft Purchase Invoice per supplier and Sales Invoice per customer from closed cards, diesel fills and transports, logged in GL Posting Log | Backend | Implemented, not visible | `card/gl/posting.py` `post_month` / `rebuild_month` (no Desk button or form script calls them); `card/tests/test_s3_posting.py` | A Desk screen with preview before creating drafts (Owner decision 2026-10-19) |
| FR-005 | Equipment needs: operator request → supervisor review → manager approval → draft ERPNext Material Requests with project, cost center and Card Equipment | Backend + Desk | Implemented | `card/materials.py` `approve_review`; `card/tests/test_v4_materials.py` | Not exercised with real data on the dev site |
| FR-006 | Separation of duties: whoever created or entered a monthly card never approves it, enforced on the server | Backend | Planned | Owner decision 2026-10-19. Today `Card Monthly Card.before_submit` checks only the customer on billing cards; no Workflow | Design and implementation |
| FR-007 | Money on monthly cards visible only to authorised roles | Backend + Desk + Mobile | Planned | Today all 10 Currency fields on Card Monthly Card are permlevel 0, so anyone who can read a card sees its amounts | Design before any operator access to cards |
| FR-008 | Overtime hours on cards | Backend + Desk | Removed | Existed in the code line before the 2026-10-12 rebuild; not on `main` | Owner 2026-10-19: restore after reviewing the calculation |
| FR-009 | Downtime hours and downtime reasons on cards | Backend + Desk | Removed | Same as FR-008 | Owner 2026-10-19: restore and link to cards |
| FR-010 | Quantity / cubic-metre billing | Backend + Desk | Removed | Same as FR-008 | Owner 2026-10-19: support several billing types per contract |
| FR-011 | Card review and approval flow (draft → review → approved, return with reason) | Backend + Desk | Removed | Same as FR-008 | Owner 2026-10-19: official design together with FR-006 |
| FR-012 | Card payment rows and Payment Entry creation from the card | Backend | Removed | Same as FR-008 | Owner 2026-10-19: only after a separate accounting design; no direct restore |

## Change log of this file

| Date | Change |
|---|---|
| 2026-10-19 | Registry created with FR-001 and FR-002 |
| 2026-10-19 | FR-001 merged (PR #77); rules for stable IDs and no deletion; FR-003 to FR-012 added from the 2026-10-19 feature audit, each checked against `main` @ `dc57259` |
