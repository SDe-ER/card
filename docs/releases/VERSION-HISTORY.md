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
| **v1.2.2** | 2026-10-18 | Security/integrity patch | Company isolation (registries + posting endpoints), protected equipment fields, permanent GL Posting Log, reconciliation in three figures | [v1.2.2.md](v1.2.2.md) |
| **v1.2.1** | 2026-10-16 | Patch | Filtered reports for operational roles, correct money on prints, sided supplier/customer totals | [v1.2.1.md](v1.2.1.md) |
| **v1.2.0** | 2026-10-16 | Feature release | Rental directions + customer side, Card Settings/roles, diesel & transport, 3 rate bases, accounting dimension, opt-in draft postings, i18n (ships the untagged v1.1 line) | [v1.2.0.md](v1.2.0.md) |
| **v1.0.1** | 2026-10-13 | Hotfix | Frappe 16.50/16.51 migrate compatibility, sidebar fold, net_amount backfill | [v1.0.1.md](v1.0.1.md) |
| **v1.0.0** | 2026-10-13 | First release | Standalone app at production parity: equipment master, assignments, monthly cards, supplier reports, workspace | [v1.0.0.md](v1.0.0.md) |

## Versions that were planned or internal but never published

| Label | Status | Note |
|---|---|---|
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
