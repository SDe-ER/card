# CARD Release Documentation Policy

**Rule: NO RELEASE WITHOUT COMPLETE VERSION DOCUMENTATION.**

A tag `vX.Y.Z` may only be pushed when every item below is updated in the same release PR. The
GitHub Release body is generated automatically from the CHANGELOG section by
`.github/workflows/release.yml`, so the CHANGELOG section must be release-ready text.

This checklist is part of the
[Change, Versioning & Safe Rollback Policy](../governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md), which also covers
every change between releases, deployments and rollback.

## Checklist for every release PR

1. **CHANGELOG.md** — a `[X.Y.Z] — YYYY-MM-DD` section following Keep a Changelog
   (Security / Added / Improved / Fixed / Removed / Replaced / Simplified as applicable, plus
   **Migration** and **Known limitations**).
2. **`docs/releases/vX.Y.Z.md`** — the full version page with all 14 sections: Version Overview,
   Complete Feature Inventory (everything present, not only the delta), Added, Improved, Fixed,
   Removed, Replaced, Simplified, Breaking Changes, Known Limitations, Compatibility,
   Installation & Upgrade, Recommended For, Evidence.
3. **`docs/releases/VERSION-HISTORY.md`** — new row in the releases table.
4. **`docs/releases/VERSION-COMPARISON.md`** — new column/notes for every feature the release adds
   or changes.
5. **`docs/releases/WHICH-VERSION.md`** — recommendations re-checked (the newest version is not
   automatically recommended for every situation).
6. **README.md** — Release History table row, release badge, and any version-named examples.
7. **Upgrade notes** — patch list, what migrate writes and does not write, rollback statement (last stable
   version, whether the previous version can run on the migrated data, and the restore or forward-fix plan; see
   the policy's "Safe rollback" section).
8. **Version bump** — `card/__init__.py` `__version__` (single source; pyproject is dynamic).

## Truthfulness rules

- Never describe a planned or unimplemented capability as available. Planned work lives only under
  `CHANGELOG.md → [Unreleased] → Planned`.
- Every documented capability uses one of these labels where certainty matters:
  **Verified** (evidence linked: code at the tag, PR, CI run, test output),
  **Partially Verified** (works, but evidence covers part of the claim),
  **Unknown** (no evidence either way — say so explicitly),
  **Not Supported**, **Deprecated**, **Removed**.
- A claim that cannot be proven is written as unverified — never invent detail to complete a table.
- **Published ≠ deployed**: release pages state publication facts only; deployment to any site is a
  separate, site-verified fact.
- Release history is immutable: never rewrite an old tag, an old CHANGELOG section's substance, or
  a published release's recorded facts. Corrections are made as dated errata in the newer release's
  page (or a dated note in the old page clearly marked as added later).

## Evidence standard

Each version page's **Evidence** section links at minimum: the tag/release URL, the CHANGELOG
section, the merged PRs (first-parent merges between the previous tag and this one), and the test
evidence actually run (CI checks, suite counts). Claims about file-level content cite
`git show <tag>:<path>` / `git ls-tree <tag>`.
