# CARD — Version History

Authoritative index of every **published** CARD release. Source of truth: git tags on
[SDe-ER/card](https://github.com/SDe-ER/card/tags) and the
[GitHub Releases](https://github.com/SDe-ER/card/releases) created from them. Each release page in
`docs/releases/` documents the full capability of that version, not only the delta.

> **Published ≠ deployed.** A version listed here is a published GitHub release. Which version runs
> on a given site is a deployment fact, verified on that site — never inferred from this file.

## Published releases

| Version | Date (tag/release) | Type | One-line summary | Full page |
|---|---|---|---|---|
| **v4.2.2** | 2026-10-27 | Patch | Diesel meter photos shown as a large card in place of the file link (change and remove on an editable fill); Arabic reading labels name the fill meter | [v4.2.2.md](v4.2.2.md) |
| v4.2.1 | 2026-10-27 | Patch | Simpler diesel fill form: fill, meter readings and equipment first; details, exception, import and posting sections collapsed or shown only when relevant | [v4.2.1.md](v4.2.1.md) |
| v4.2.0 | 2026-10-27 | Minor release | Diesel fill as a metered session with meter photos and an operations review; import of reviewed WhatsApp diesel sessions as drafts with the supplier invoice price; parts fitment in the catalog; app name CARD in every language; backdated transports cannot drop submitted card days | [v4.2.0.md](v4.2.0.md) |
| v4.1.2 | 2026-10-25 | Patch | Launcher shows all ten sections on sites with an old dock layer; simpler Equipment Transport form; English for stored Arabic values; missing Arabic strings | [v4.1.2.md](v4.1.2.md) |
| v4.1.1 | 2026-10-25 | Patch | Tool Custody item search works without an ERPNext Item permission (scoped `item_query` endpoint) | [v4.1.1.md](v4.1.1.md) |
| **v4.1.0** | 2026-10-25 (tag after the release PR merge) | Minor release | First production go-live candidate (P1–P3): unique chassis/plate numbers per company, upgrade rehearsal from v1.0.1, company-isolation and concurrency fixes; also CARD Mobile foundation (not device-tested), catalog search, fitment 2a, tool handover, diesel price lock | [v4.1.0.md](v4.1.0.md) |
| **v4.0.0** | 2026-10-19 | Major release | Equipment materials: operator page for machine needs, supervisor review, management approval into draft ERPNext Material Requests with project, cost center and equipment dimension, employee tool custody, 4 reports | [v4.0.0.md](v4.0.0.md) |
| **v3.0.0** | 2026-10-19 | Major release | CARD launcher (Dock + 9 sidebars), multi-machine transport with destinations and destination cost center, monthly card follows approved transports, equipment details from the ERPNext Asset, dated unit components | [v3.0.0.md](v3.0.0.md) |
| **v1.2.2** | 2026-10-18 | Security/integrity patch | Company isolation (registries + posting endpoints), protected equipment fields, permanent GL Posting Log, reconciliation in three figures | [v1.2.2.md](v1.2.2.md) |
| **v1.2.1** | 2026-10-16 | Patch | Filtered reports for operational roles, correct money on prints, sided supplier/customer totals | [v1.2.1.md](v1.2.1.md) |
| **v1.2.0** | 2026-10-16 | Feature release | Rental directions + customer side, Card Settings/roles, diesel & transport, 3 rate bases, accounting dimension, opt-in draft postings, i18n (ships the untagged v1.1 line) | [v1.2.0.md](v1.2.0.md) |
| **v1.0.1** | 2026-10-13 | Hotfix | Frappe 16.50/16.51 migrate compatibility, sidebar fold, net_amount backfill | [v1.0.1.md](v1.0.1.md) |
| **v1.0.0** | 2026-10-13 | First release | Standalone app at production parity: equipment master, assignments, monthly cards, supplier reports, workspace | [v1.0.0.md](v1.0.0.md) |

## Versions that were planned or internal but never published

| Label | Status | Note |
|---|---|---|
| v2.x | **Never existed** | The version jumped from 1.2.2 to 3.0.0 by owner decision (the "CARD Unified UX" design named it 3.0.0) |
| v1.1 | **Not released** | Developed and merged on `main`, never tagged; its content ships in v1.2.0 (stated in the v1.2.0 release notes and README) |
| v0.0.1 | **Not released** | Bench scaffold `__version__` packaged inside the v1.0.0 tag only — not a tag or release |

Any other version number found in local clones or working documents (e.g. stale local-only tags) is
**not a CARD release** unless it appears on the GitHub tags/releases pages above.

## Release mechanics (current, Verified)

- Annotated tag `vX.Y.Z` on the release-PR merge commit on `main`.
- `.github/workflows/release.yml` creates the GitHub Release "Card vX.Y.Z" automatically on tag
  push, with the body extracted from that version's `CHANGELOG.md` section — so the CHANGELOG
  section **is** the release description; keep them as one text.
- Single version source: `card/__init__.py` `__version__` (pyproject `dynamic = ["version"]`).

## Related pages

- [Version Comparison Matrix](VERSION-COMPARISON.md)
- [Which Version Should I Use?](WHICH-VERSION.md)
- [Release Documentation Policy](RELEASE-POLICY.md)
- [CHANGELOG](../../CHANGELOG.md)
