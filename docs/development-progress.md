# CARD development progress

Checkpoint written from a live GitHub audit on 2026-11-16 (read-only). Re-verify against GitHub before acting on any item.

## Versions

- Latest GitHub release: **v4.9.0** (`Latest`, published 2026-11-15).
- Latest tag: **v4.9.0** (commit `660633b`).
- `main` after PR #273: contains the v4.10.0 dashboard work (merge `5f0ef52`). **Not released.** The application version in `main` is still `4.9.0`.
- Next version if released: **4.10.0** (MINOR: new backward-compatible dashboard feature, FR-168).
- Production: last recorded version v4.9.0 deployed 2026-11-15 (see `docs/releases/DEPLOYMENTS.md`). One equipment data step was left open there.

## Audit summary (2026-11-16)

- Open Issues: **31**.
- Open PRs: **5** (3 Dependabot action bumps, 2 feature PRs with merge conflicts).
- Merged today: #267 (screenshots), #268 (review copy FR-167), #269 (Search Console tag), #270 (screenshots removed), #271 (v4.9.0 release), #272 (deployment record), #273 (v4.10.0 dashboard).

## Backlog classification

Priority follows the mandate: P0 critical (data, accounting, security, production-blocking); P1 high (accounting correctness, major defects, important integrations); P2 medium; P3 low.

### Security and data integrity (first in order)

| Item | Type | Priority | Status | Note |
|---|---|---|---|---|
| #257 Security review: ignore_permissions and other findings on main | Security | P0 | Blocked | The issue says any fix needs separate owner approval. Findings are in a private report. |
| #259 Harden Equipment Customer Statement: field-level permlevel checks | Security | P1 | Ready | No new role has access today. Add explicit field checks before any new role is granted. |

### Accounting and data (P1)

| Item | Type | Priority | Status | Note |
|---|---|---|---|---|
| #263 FR-166 period-run fingerprint v2 must include loads | Bug (accounting) | P1 | Ready to analyse | Period-run fingerprint must change when loads change, or a closed period can hide a change. |
| #264 FR-166: explicit include_loads and loads column only on per-m³ cards | Bug/Enhancement | P1 | Ready to analyse | Affects reports and the customer statement. |

### Existing PRs

| PR | Title | State | Priority | Action |
|---|---|---|---|---|
| #245 | bump actions/checkout 4 to 7 | Dependabot | P3 | Validate CI on the PR; check the Pages workflow is unaffected. Needs owner approval to merge. |
| #244 | bump actions/deploy-pages 4 to 5 | Dependabot | P3 | Touches the Pages deploy. Owner approval to merge; verify docs build. |
| #243 | bump actions/upload-pages-artifact 3 to 5 | Dependabot | P3 | Same as #244. |
| #237 | feat(reports): Equipment Customer Statement A4 print (FR-149) | DIRTY, +520 -1, last update 2026-11-10 | P2 | Rebase onto main, review against FR-162 money rules, then test. Owner decision: rebase or supersede. |
| #225 | feat(owners): third-party owners and Crusher Owner Statement (FR-150) | DIRTY, +4832 -15, last update 2026-11-10 | P2 | Large and stale. Needs an owner decision before any rebase. |

### Go-live epic and phases (blocked on production acceptance)

| Item | Status |
|---|---|
| #118 epic | Blocked: owner rollout decisions. |
| #119 P0 production readiness, migration rehearsal, rollback | Blocked: needs owner approval for any production or rehearsal step. |
| #120 to #127 P1 to P8 live acceptance | Blocked: each phase needs owner acceptance in real use. |

### Documentation and screenshots

| Item | Status |
|---|---|
| #266 Docs screenshots: demo data and volume-billing set incomplete | Blocked: needs owner approval for a new capture run. Screenshots are pending, not fabricated. |

### Features and epics (triage needed, P2/P3)

| Items | Status |
|---|---|
| #231 fuel: site tank and bulk delivery inventory | P2, large feature. Triage with owner. |
| #54, #53, #52, #51, #50, #49, #48, #46, #45, #44, #43, #42, #40, #35, #31 | Older epics and features (2026 planning). Likely partly superseded by shipped work (for example volume billing, review copy, workspace). Each needs an owner triage decision. Do not close without checking which parts are shipped. |

## Blocked tasks (with exact blocker)

- #257: fixes need separate owner approval (Issue text).
- #119 to #127, #118: production acceptance and rollout decisions (owner).
- #266: a capture run needs owner approval; no QA or dev site is used for screenshots.
- #237 and #225: merge conflicts; owner decision on rebase or supersede.

## Screenshots

- Status: **pending**. No real CARD screenshots of the v4.10.0 dashboard have been captured. The dashboard was verified in code and tests only, not on a Desk.

## Latest test run

- PR #273 (`80a1b58`): CI green, including CARD unit tests (frappe version-16 / 16.5x), Upgrade rehearsal, Semgrep, CodeQL, pre-commit.

## Next planned action

1. Analyse #263 and #264 against the code (FR-166 period-run fingerprint and per-m³ loads); write failing tests first.
2. Validate Dependabot PRs #243 to #245 on CI; report before merging.
3. Owner triage of #225 and #237 (rebase or supersede), and of the older epics.

## Release status

- v4.10.0 is merged to `main` but not released. A release (release PR, tag, GitHub Release) needs an explicit owner instruction for that step, and a separate Production deployment approval.
