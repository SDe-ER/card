# CARD architecture pack

**Status: documentation only.** Epic #40 (CARD as an HRMS-grade equipment operations platform) and issue #54 (HRMS
v16 parity audit and global acceptance suite) ask for a set of architecture documents. This directory holds them.
Nothing here changes code, data, permissions or accounting. It does not replace the owner's sign-off that #54
requires before coding.

Baseline: `main` @ `8ededce`. Every fact below was read from the code at that commit: DocType JSON under
`card/card/doctype/`, the controllers next to them, `card/hooks.py`, `card/gl/*`, `card/patches/`, `card/settings.py`
and `card/constants.py`. Paths are relative to the repository root. Line numbers are deliberately not used (they drift);
search for the function name. Where the code does not implement something, the text says **Planned** with the issue
number. A plan is not an implementation.

All examples use generic names ("Company A", "Supplier X", "Customer Y", "Project P1"). No real company, party, person,
host or tax number appears in this pack.

## What #40 and #54 ask for, and where it is answered

| Requested document (source) | File | Notes |
|---|---|---|
| Domain map (#40 delivery) | [01-domain-map.md](01-domain-map.md) | DocTypes, how they link, and where CARD stops and ERPNext starts |
| State transitions (#40 delivery) | [02-state-transitions.md](02-state-transitions.md) | One section per DocType that has a lifecycle |
| Source-of-truth matrix (#40 delivery, #54 acceptance) | [03-source-of-truth-matrix.md](03-source-of-truth-matrix.md) | One owner per fact, and what is derived |
| Localization matrix (#40 principle 3) | [04-localization-matrix.md](04-localization-matrix.md) | Language, currency, tax, units, time, direction |
| Accounting examples (#40 delivery) | [05-accounting-examples.md](05-accounting-examples.md) | Which ERPNext documents CARD creates, with example lines. CARD never writes GL |
| Risk register (#54 acceptance) | [06-risk-register.md](06-risk-register.md) | Migration, accounting, permission and data risks |
| International test matrix (#54 requirements) | [07-international-test-matrix.md](07-international-test-matrix.md) | What exists, what is missing |
| Phased roadmap (#40 delivery, #54 acceptance) | [08-roadmap.md](08-roadmap.md) | Maps open issues to the go-live phases of #118 |

## Asked for, but not in this pack

| Item | Where it lives or will live |
|---|---|
| Permission matrix (#40 delivery) | [docs/governance/ROLE-ACTION-MATRIX.md](../governance/ROLE-ACTION-MATRIX.md), written separately. Not duplicated here |
| HRMS v16 gap analysis with file and line references (#40, #54) | [docs/governance/HRMS-PARITY.md](../governance/HRMS-PARITY.md) (already on `main`) |
| Settings and hardcoded constants inventory (#50) | [docs/governance/SETTINGS-AND-CONSTANTS.md](../governance/SETTINGS-AND-CONSTANTS.md) |
| Intake provenance design (#52) | [docs/governance/INTAKE-PROVENANCE-DESIGN.md](../governance/INTAKE-PROVENANCE-DESIGN.md) |
| Migration strategy from v1.0.1 and rehearsal | Rehearsal exists as a CI job (#130). The written strategy and rollback limits are in the [policy](../governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md) and [risk register](06-risk-register.md) section 1 |
| Feature status (what is implemented, in review, planned) | [docs/governance/FEATURE-REGISTRY.md](../governance/FEATURE-REGISTRY.md). This pack does not edit it |

## How to keep this pack true

- When a DocType, state, hook, posting rule or setting changes, change the matching file in the same pull request.
- Do not copy a status from here into the registry; the registry is the single place for feature status.
- A statement that is not backed by a file in the repository must be marked **Planned** or removed.
