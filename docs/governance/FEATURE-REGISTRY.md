# CARD Feature Registry

The permanent record of CARD features and fixes: what exists, where it lives, how it is proven, and what is still
open. It exists so that no working feature is lost silently during a rebuild or refactor.

## Rules

- Every task that adds, changes, fixes or removes a feature updates this file in the same task.
- Before closing a task: compare the affected features with the current code, confirm no earlier feature was lost,
  and record the evidence (PR, commit, tests). A task is not closed until this file is updated, or the reason it
  could not be updated is written here.
- Never mark a feature as available unless it is merged to `main` and covered by tests. Planned work stays
  **Planned**.
- Browser and real-device checks are recorded separately; a passing unit test is not a visual check.

## Status values

| Status | Meaning |
|---|---|
| Implemented | Merged to `main`, covered by tests |
| In review | Open pull request, not merged |
| Planned | Approved, design or code not finished |
| Implemented, not visible | Code exists but users have no entry point |
| Broken | Confirmed defect in `main` |
| Removed | Existed before, intentionally taken out (state the replacement) |

## Registry

| ID | Feature | Layer | Status | Evidence | Open points |
|---|---|---|---|---|---|
| FR-001 | Diesel fill form works for Card User: the supplier lock comes from the server (`get_supplier_editable`, yes/no only); Card Settings stays closed to fill users | Desk + Backend | In review | PR #77 (commit `13aaf46`); `card/tests/test_settings_wiring.py` TestDieselSupplierPolicy (6 new tests); dev-site suite 490 tests, only 3 dev-data `test_baseline_regression` failures that also fail on `main`; CI on PR #77: 8/8 checks pass (490 tests OK, 20 skipped), 0 code-scanning alerts | Browser check of the form not done; merge awaiting Owner approval |
| FR-002 | Diesel price per company: kept in Card Company Settings, filled automatically into every fill, not editable by Card User, save refused when no approved price exists (legitimate exceptions to be defined), authorised override with mandatory reason and audit trail, old fills never recomputed | Backend + Desk | Planned | Design under review (separate task). Today on `main`: the company price is copied only when the fill price is blank, and any user may type a price | Design approval; implementation; tests; browser check |

## Change log of this file

| Date | Change |
|---|---|
| 2026-10-19 | Registry created with FR-001 and FR-002 |
