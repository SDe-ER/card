# Which Version Should I Use?

The latest release is not automatically the right one for every site. Pick by compatibility and
need; every claim below is backed by the per-version pages (evidence links there).

## Quick answer

| Your situation | Use | Why |
|---|---|---|
| New install, Frappe/ERPNext **v16.5x** | **v1.2.2** | Latest; all v1.2 features plus company isolation, protected equipment fields, permanent posting audit log |
| **Multi-company** site (any) | **v1.2.2 only** | v1.2.0/v1.2.1 registries expose party-wide totals across companies (#23, fixed in v1.2.2) |
| Site with operational (non-accounting) users running filtered reports | **v1.2.1 or later** (prefer v1.2.2) | Before v1.2.1 a Card User could not filter reports by supplier/customer/project (#21) |
| Frappe v16 **below 16.50** (e.g. 16.33–16.4x) | **v1.0.1** | Last version validated on pre-16.50 minors; v1.2.x is tested on 16.5x only (earlier minors: Unknown) |
| Only the original supplier monthly-card workflow, no accounting/customers/diesel | **v1.0.1** (pre-16.50) or **v1.2.2 with accounting off** (16.5x) | v1.2.2 keeps accounting off by default; the classic workflow is unchanged |
| Must match what is verified deployed on SDCE production (as of 2026-10-18) | **v1.0.1** | The only version with a verified production deployment (2026-10-13). v1.2.x is published, not deployed |

## Never use

- **v1.0.0** on Frappe ≥ 16.51 — `bench migrate` fails (fixed in v1.0.1).
- **v1.2.0 / v1.2.1** on multi-company sites — registry totals are not company-isolated (#23).
- Any version number that has no tag + GitHub Release on SDe-ER/card — it is not a CARD release
  (see [VERSION-HISTORY.md](VERSION-HISTORY.md)).

## Upgrade path

- `v1.0.x → v1.2.2` directly: supported and tested; all `v1_2`, `v1_2_1`, `v1_2_2` patches run once,
  idempotently ([v1.2.2.md → Installation & Upgrade](v1.2.2.md#12-installation--upgrade--verified)).
- Always rehearse `bench migrate` on a restored copy of production first; a migrate that fails on
  the copy must never be run on production (README → Upgrading).
- Downgrades are not supported by patches; rollback = restore the pre-upgrade backup.

## Things the latest version still does not do (so you don't choose it for the wrong reason)

- No automatic matching of external ERPNext invoices to cards — "invoices outside Card" are listed
  for **manual** reconciliation only (v1.2.2).
- Diesel **cost** totals mix recorded and estimated amounts (litres are split; #33 partially fixed).
- Full-day billing for the per-day rate basis is **Planned** (Unreleased), not available: the
  per-day basis bills hours-prorated.
- Broader accounting phases (activation workflow, tax classes, claims, allocation shares) are an
  approved design, not shipped.
