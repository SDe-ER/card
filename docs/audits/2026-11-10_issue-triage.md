# Issue triage — SDe-ER/card, 2026-11-10

Status: **Approved by the owner as drafted, 2026-11-10.** Owner decisions on the rows are in section 4. When this
matrix was written, no issue was closed, commented on or changed, and no code was changed.

Baseline: `origin/main` @ `fe1e1b6` (fetched 2026-11-10). Production runs v4.7.0 (`e566174`, PR #206).
PRs #207–#226 are merged on `main` but **not released and not on Production**.
Method: issue text and the 2026-10-26 triage comments, merged PR bodies (#186–#226), `CHANGELOG.md`,
`docs/governance/FEATURE-REGISTRY.md`, `docs/architecture/*`, and spot greps on `main`.
Evidence level: SOURCE. Nothing here is a runtime or acceptance result.

Legend — STATUS: DONE / PARTIAL / NOT STARTED / OBSOLETE / OWNER-ACCEPTANCE.
"Rel" = released and live (v4.6.0/v4.7.0); "Unrel" = on `main` only.

## 1. Open pull requests (Phase 0)

| PR | Title | State (2026-11-10 19:21 UTC) | Proposed action |
|---|---|---|---|
| #227 | fix(security): child-table permlevel on reads (FR-148) | CI running; new commit 19:14 UTC by another active session | Let that session finish; merge after CI green + owner GO |
| #228 | fix(transport): keep intake evidence (FR-146) | CI running; commit 19:02 UTC; branch behind main | Same as #227 |
| #225 | feat(owners): third-party owners, Crusher Owner Statement | Merge conflicts (DIRTY); reuses FR-147 (also used by #222) | Rebase, renumber FR id; needs owner answers Q1–Q9 of the plan |
| #229 | docs: documentation site (Astro Starlight) | CI running | Owner decision: GitHub Pages site is public |
| #219 | docs(releases): record v4.7.0 deployment | Behind main, checks green | Update branch, merge after owner GO |

None of these PRs carries `Closes #N` for an open issue except references (`Refs #52, #43` on #228).

## 2. Issue matrix

| Issue | Title (short) | STATUS | Evidence / what remains | RELEVANT_TO_SDCE | PROPOSED_ACTION |
|---|---|---|---|---|---|
| #31 | Diesel epic | PARTIAL | Done: FR-125 #195, FR-126 #196, FR-100 #163 (Rel); FR-128 #200 (Rel); FR-132 #209, FR-140 #217, FR-144 #223 (Unrel). Remains: allocation rows, variance/anomaly report, daily litres on card, tanks/dip, operating groups. Owner decisions D1–D7, FR-033, FR-034 open | yes — diesel is a major SDCE cost | **owner decision** (rule-7 conflict), then implement or split |
| #35 | Governance epic G0–G4 | PARTIAL | Done: FR-123 #197, FR-124 #198 (Rel), FR-129 #203 (Rel), FR-137 #207, FR-143 #224, FR-131 #208 (Unrel). Remains: Workflow (G1), block of direct submit, reviewer permissions, G2 price approval, G3 thresholds, G4 delegation | yes — accountability on cards and money | implement per phase; each G-phase needs its own owner GO (WS-020) |
| #40 | Architecture umbrella | PARTIAL | Docs pack #202 (Rel), HRMS-PARITY / SETTINGS / INTAKE design #186 (Rel). Remains: owner sign-off | yes | **owner sign-off** then close-done |
| #41 | Contracts, multiple customers, responsibility | PARTIAL | FR-141 Card Rate Agreement #216 (Unrel, unwired). Remains: wiring, several customers per project, ambiguity block, responsibility in billing. FR-023 postponed by owner 2026-10-19 | yes, but owner postponed it | **owner decision**: keep postponed (open) or descope |
| #42 | Equipment master, ownership, yard, unit | DONE (residual) | FR-115/116 #187, FR-122 #191 (Rel). Residual to verify: "no operation cards while parked" | yes | verify residual, then close-done |
| #43 | Single transfer, location history | PARTIAL | FR-117 #187, FR-120 #190 (Rel), FR-130 #201 (Rel), FR-139 #215, FR-146 #220 (Unrel). Remains: controlled correction flow; move-day owner decision (WP-15); #228 | yes | owner decision (move day) + implement correction flow |
| #44 | Daily input, monthly cards, generation | PARTIAL | FR-142 #218/#226, FR-145 #221, FR-138 #214 (Unrel). Remains: agreement in card key (needs #41), overtime (FR-008), quantity billing (FR-010), mobile entry | yes | implement after owner decisions FR-008/FR-010/O-06 |
| #45 | Stop reasons, no auto entitlement | DONE (Unrel part) | FR-118 #194 (Rel), FR-134 #212 (Unrel), DOWNTIME-MINIMUM-GUARANTEE.md. Owner to confirm default O-03 | yes | close-done after release + owner confirms O-03 |
| #46 | Dated fuel price, fill snapshot | DONE (Unrel part) | FR-125 #195 (Rel), FR-132 #209 (Unrel), FR-127 #199 (Rel). Named limit: one fuel type only | yes | close-done after release (second fuel type → new issue only if owner wants) |
| #47 | Bulk delivery, tank inventory | NOT STARTED | Requirement "allocate 1,180 L by hours × L/h" conflicts with #118 rule 7 and FR-100 | partly — tanks yes; invented split no | **owner decision** (conflict with an approved rule) |
| #48 | Equipment-centric costs | PARTIAL | FR-112/114 #188, FR-120 (Rel). Remains: capture of maintenance/parts/oils with source docs, multi-equipment allocation, payer per category | yes | implement (P7); native ERPNext docs only |
| #49 | Period approval, invoice drafts | PARTIAL | FR-119 #193 (Rel), FR-147 Period Run #222, FR-136 #210 (Unrel). Remains: posting requires approved run (opt-in), credit-note path, customer transport charge (O-14 tax adviser) | yes — accounting | implement (accounting, high-risk) after O-14/FR-030/FR-012 decisions |
| #50 | Centralized configuration | PARTIAL | Inventory #186, FR-124, FR-127 (Rel), FR-133 #213, FR-135 #211 (Unrel). Remains: effective dates for changing settings; leftover constants | yes | implement (small) |
| #51 | Lifecycle, roles, portals | PARTIAL | `methods=` on all whitelists #161 (Rel), FR-129, FR-121 (Rel). Remains: workflow tests (needs #35 G1), supplier/customer portals, #227 | portals: unclear for SDCE | implement non-portal part; **owner decision** on portals |
| #52 | Intake paper/WhatsApp | PARTIAL | Diesel import #140 (Rel), FR-146 #220 (Unrel). Remains: card-day/daily-log provenance, intake register, unauthorized sender handling, #228 | yes | implement |
| #53 | Profitability, reporting | PARTIAL | FR-112/113/114 #188, FR-118, FR-130 (Rel), FR-136 currency label (Unrel). Remains: project profitability, fuel delivered vs estimated (needs #31), zones (needs #41), currency policy | yes | implement after #31/#41 |
| #54 | HRMS parity, acceptance suite | PARTIAL (nearly done) | HRMS-PARITY #186, pack #202, rehearsal #192, FR-136 suite #210. Remains: owner sign-off; v1.0.1 migration text obsolete (Prod is 4.7.0) | yes | **owner sign-off** then close-done |
| #118 | Go-live epic | OWNER-ACCEPTANCE | Closes when #119–#127 are accepted | yes | close after all phases accepted |
| #119 | P0 readiness/rollback | OWNER-ACCEPTANCE | Code LIVE since v4.1.2; now v4.7.0; rehearsal on every PR (#192) | yes | Arabic acceptance checklist → owner confirms in writing |
| #120 | P1 equipment registration | OWNER-ACCEPTANCE | LIVE; QA PASSED 2026-10-25 | yes | checklist → owner confirms |
| #121 | P2 transport | OWNER-ACCEPTANCE | LIVE; move-day decision open (#43) | yes | checklist → owner confirms |
| #122 | P3 assignment / cost center | OWNER-ACCEPTANCE | LIVE; same move-day decision | yes | checklist → owner confirms |
| #123 | P4 operating cards | OWNER-ACCEPTANCE | Live core; daily log/generation (#218, #221) unreleased | yes | checklist after next release |
| #124 | P5 project diesel | OWNER-ACCEPTANCE | Live core; FR-033 estimate decision open | yes | checklist after owner decision |
| #125 | P6 spare parts / tools | OWNER-ACCEPTANCE | Live; FR-121 #189 (Rel) | yes | checklist → owner confirms |
| #126 | P7 ERPNext integration | OWNER-ACCEPTANCE | Posting/period run partly unreleased | yes | checklist after next release |
| #127 | P8 analysis/reports | OWNER-ACCEPTANCE | Reports partly live; #53 open | yes | checklist after #53 |

Totals: DONE (residual) 3 (#42, #45, #46) · PARTIAL 13 · NOT STARTED 1 (#47) · OBSOLETE 0 · OWNER-ACCEPTANCE 10.

## 3. Findings outside the matrix

- `FEATURE-REGISTRY.md` rows for PRs #207–#226 still say "In review"; the PRs are merged. Registry is stale.
- FR-147 is used by two different changes (#222 Card Period Run, merged; #225 owners, open).
- An "ECC Tools" GitHub App posts audit comments on PRs, although ECC was removed locally on 2026-10-16.
- Closure-plan ids (WP-*, O-xx, W-15) are cited in the registry but the plan file is not in the repo.

## 4. Owner decisions (2026-11-10)

- #31 / #47: keep #118 rule 7. No hours × L/h allocation (not planned). Tank and bulk inventory with measured
  readings only stays in scope (#231). **Under review (second batch):** the owner reported a conflict with an
  earlier approval (2026-10-12, allocation by working hours). Proposed: allocation allowed but stored and shown as
  estimated; measured fills take precedence and are never overwritten. #47 reopens for the allocation part only if
  the owner confirms.
- Move day (second batch, approved): on a project → project move the move day counts for the new project (#43,
  #121, #122). FR-117 `move_day_rule` already supports it per company; setting it on Production waits for an
  explicit "execute".
- #41: not planned — postponed by the owner on 2026-10-19 (FR-023). The parts of #44 and #53 that depend on it are
  postponed with it.
- #51: full scope, including the supplier/customer portal, built but off by default (second batch; the first
  instruction "portals not planned" was withdrawn because it reversed an earlier approval).
- #42, #45, #46: verify the residuals, then close as done with evidence after the next release.
- #40, #54: owner sign-off in writing.
- #118–#127: each closes only after the owner confirms acceptance in writing.
- #229: no public GitHub Pages site.
