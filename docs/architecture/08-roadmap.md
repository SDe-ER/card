# Roadmap

This is a mapping, not a decision. The order of release work is set by the owner in issue #118 (go-live): #119 (P0
readiness) then #120 (P1 equipment), #121 (P2 transport), #122 (P3 project assignment), #123 to #127. The epic #40
(with #54 merged into it, section 4) adds design work around that order; it does not reorder it. An optional improvement never blocks a phase: it goes in
the backlog, linked to its phase (`AGENTS.md`).

"Exists" means present in code at `main` @ `8ededce` and listed in the registry; it does not mean live. Status is owned
by [FEATURE-REGISTRY.md](../governance/FEATURE-REGISTRY.md). A phase closes only after its acceptance criteria pass in real
use with evidence and the owner's approval (#118).

## 1. Go-live phases (#118) and the architecture they depend on

| Phase | Issue | Scope in this pack | Architecture facts to confirm before approval |
|---|---|---|---|
| P0 readiness | #119 | Migration, rollback, deployment checklist | [Risk register](06-risk-register.md) R-01, R-02, R-04, R-20; accounting dimension step; verified backup and written rollback plan |
| P1 equipment | #120 | Card Equipment master, status, ownership, direction | [State transitions](02-state-transitions.md) section 2; R-18; identity keys and Asset link in the [matrix](03-source-of-truth-matrix.md) |
| P2 transport | #121 | Equipment Transport, move-day rule, cost responsibility | State transitions section 4; accounting examples section 6; R-08 |
| P3 project assignment | #122 | Assignments, derived location, cost centers | State transitions section 3; source-of-truth section 1; R-19 |
| P4 operating cards | #123 | Monthly Card, rates, additions and deductions | State transitions section 5; R-09, R-10, R-12, R-13 |
| P5 project diesel | #124 | Diesel fill, price, review, import | State transitions section 6; R-22; price schedule (FR-125, #46) |
| P6 spare parts and tools | #125 | Needs request, review, custody, fitment | State transitions sections 9 to 11; accounting examples section 7 |
| P7 ERPNext integration | #126 | Posting to Purchase and Sales Invoice, settlement, stock | [Accounting examples](05-accounting-examples.md); R-05, R-06, R-07; international test rows 6, 13, 15 |
| P8 reports | #127 | Full system analysis and reports | Reports in the domain map; reconciliation module; R-12, R-25 |

## 2. Feature epics (#41 to #53) against the code

| Issue | Title (short) | What exists | What is Planned | Depends on |
|---|---|---|---|---|
| #41 | Project contracts, multiple customers, responsibility matrix | Customer on equipment and card; transport cost bearer | Contract DocType, several customers per project, responsibility matrix, supplier-specific terms | Owner model decision; P2 and P4 |
| #42 | Equipment master, ownership, yard, combined unit | Master, ownership rules, combined units of owned pieces, identity keys, status guard (FR-122), configurable initial location (Card Company Settings `initial_location`) | Open points are those listed in the issue (for example no operation cards while parked); confirm each against the registry before P1 | P1 |
| #43 | Single authoritative transfer, effective-dated location | Transport drives assignments; move-day rule; derived location; cancel guards | Arrival-date semantics: the issue asks for one effective date equal to arrival; the code applies the company move-day rule (WP-15; owner decision 2026-11-24: the move day counts for the new project, a company setting). Controlled correction flow for conflicting historical changes | P2, P3 |
| #44 | Daily input, monthly cards, project splits, generation | Monthly Card with day rows; project derived from assignments | Automatic generation, project splits within a month, daily log (FR-022) | P4 |
| #45 | Configurable stopped reasons, no automatic entitlement | Card Stop Reason (billable off by default), stop reason and stopped hours on the day row, 24-hour cap, billable stopped hours on the card, Equipment Downtime report, seed patch (FR-118, PR #194 merged) | User-extensible day-status table with billable flags (FR-061) is a different, still Planned request | P4 |
| #46 | Effective-dated fuel price, immutable fill snapshot | Company price on fill (FR-002); price schedule (FR-125) in `[Unreleased]` | Unit and currency snapshot on each fill (the issue asks for both; the price is fixed on the fill today, the unit is not recorded); fuel type; configurable unit | P5 |
| #47 | Bulk delivery allocation, tank inventory | Per-fill diesel only | Delivery, tank, measured-vs-estimated provenance (FR-034) | Owner model decision |
| #48 | Equipment-centric maintenance, transport and operating cost | Reports over ERPNext expenses and the dimension | Capture of maintenance, parts, oils and miscellaneous expenses with source documents; multi-equipment allocation of one expense | P7 |
| #49 | Period approval with native invoice drafts | Monthly posting builds draft invoices | A period approval document before billing; credit-note path; customer transport billing | P7; owner and tax adviser decisions |
| #50 | HRMS-style centralized configuration | Card Settings and company rows; inventory document | Effective-dated settings, setup check, per-company storage | P0 |
| #51 | HRMS-grade lifecycle, roles, approvals, audit, portals | Separation of duties in transport decision, needs review, fitment, custody | Same rule for monthly cards (FR-006); configurable approvals; external portals | P4 |
| #52 | Intake from paper and WhatsApp | Diesel session import with provenance | Same for transports and card days ([design](../governance/INTAKE-PROVENANCE-DESIGN.md)) | After P2, P4 |
| #53 | Profitability, cost provenance, global reporting | Partial margin and cost reports | Project and equipment profitability with provenance, labelled as partial contribution margin (diesel, maintenance, transport) | P8 |

## 3. Proposed architecture work, in order

These are documentation and test tasks that need no behaviour change. Each is small enough for one pull request.

| Step | Work | Phase | Issue |
|---|---|---|---|
| 1 | Owner review of this pack and of the role matrix; record decisions in the issues — decisions of 2026-11-24 recorded in section 5 | any | #40 |
| 2 | GL-neutrality test and `ignore_permissions` allow-list test — done: FR-136 `test_gl_neutrality.py` (in review), FR-129 allow-list | P7 | #54 |
| 3 | Two-company, two-currency posting test — done: FR-136 `test_two_currency_posting.py` (in review) | P7 | #54 |
| 4 | Read-only integrity report for source and log disagreement — done: FR-136 Posting Source Integrity (in review) | P7 | #54 |
| 5 | Generated role-by-action tests from the role matrix — done: FR-129 `test_bola_matrix.py`; POST-only writers: FR-136 `test_writer_methods_post.py` (in review) | P0 | #54, #51 |
| 6 | Time zone and month-end tests — done: FR-136 `test_month_end_timezone.py` (in review) | P4 | #54 |
| 7 | Model decisions needed before any code: contracts (#41), tanks (#47), period approval (#49) | after P8 | #40 |

Behaviour changes that follow from the owner's answers (separation of duties on cards, dated rates, fuel unit, country
tax settings) are separate pull requests, each opt-in per company or warn-only by default, each with a CHANGELOG entry and
a registry row, and none starts without the owner's GO.

## 4. What closes #40 (#54 is merged into it)

Owner decision 2026-11-24: issue #54 (HRMS v16 parity audit, migration compatibility, global acceptance suite) is
merged into epic #40 and closed. Its deliverables stay tracked here:

| #54 deliverable | Where it is | State |
|---|---|---|
| HRMS v16 comparison with evidence | [HRMS-PARITY.md](../governance/HRMS-PARITY.md) | Written |
| Capability map: existing, gap, reusable Frappe API | [01-domain-map.md](01-domain-map.md), section 2 above | Written; statuses in the registry |
| International test matrix | [07-international-test-matrix.md](07-international-test-matrix.md) | Written; FR-136 tests merged |
| Migration strategy from v1.0.1, rollback, rehearsal | CI job "Upgrade rehearsal" (#130), the [policy](../governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md), [risk register](06-risk-register.md) section 1 | Rehearsal runs on every pull request |
| Acceptance tests (backdating, idempotency, corrections, permissions, GL neutrality, accounting integrity) | 07-international-test-matrix.md rows 11 to 15 | In CI |
| Owner sign-off before coding | Decisions of 2026-11-24, section 5 below | Given per issue |

#40 stays open as the umbrella. It closes when every item in it is done or the owner removes it from scope. The
permission matrix is separate (`ROLE-ACTION-MATRIX.md`, FR-129).

## 5. Owner decisions of 2026-11-24

A decision is not an implementation. Status of each change is in the
[registry](../governance/FEATURE-REGISTRY.md) and the CHANGELOG.

| Issue | Decision | Effect on this roadmap |
|---|---|---|
| #31 | Estimated diesel allocation is allowed. It is always labelled "Estimated", and a measured quantity always wins | Section 2, #47: provenance rule fixed |
| #231 | A site tank is a standard ERPNext Warehouse. Card makes no postings for it | Section 2, #47: tank model decided |
| #35 | Approval workflows in stages G0 to G4. No workflow is activated on a live site without a separate owner GO | Section 2, #51 |
| #42 | Finish the small open points (combined unit for owned pieces only, initial yard per company, part-of-unit link) | P1 |
| #43 | Move-day rule: the move day counts for the new project (company setting, applied on the live site 2026-11-24). Third-party payer: deferred | P2 |
| #45 | Rule O-03 approved (a stop is charged to the customer only when its reason is marked billable). Issue closed | P4 |
| #48 | One expense for several machines is split manually | P7 |
| #50 | A zero value means "must be configured": Card warns and does not fall back to a hard-coded number | P0 |
| #53 | Three reports, in this order: equipment profitability, downtime, diesel cost per equipment | P8 |
| #264 part 2 | Loads columns only on per-m³ cards, with before/after screenshots in the pull request | P4 |
| #299 | A4 customer statement without the hourly rate, with before/after prints | P8 |
| #44, #49, #51, #52, #300 | Deferred. No work until the owner reopens them | — |
| Card Equipment accounting dimension | Created only when Card Settings switches it on (default off, FR-180) | P0, P7 |
