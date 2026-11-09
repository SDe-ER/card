# Skill substitutes — owner-approved register

[AGENTS.md](../../AGENTS.md) ("Skills") requires the official Frappe skills from https://github.com/frappe/skills.
This register lists the only substitutes an agent may use when an official skill is not available, and the review
procedure that replaces `frappe-code-review`. A substitute replaces guidance only; it never removes a review, test,
security scan, approval or Production safeguard.

## 1. Status of the official skills

| Official skill | Status (2026-11-02) | Note |
|---|---|---|
| `frappe-app-dev` | not installed | The frappe/skills repository has no license file (checked at its commit `5dc2f98`). The skill is not installed or copied until a license permits it. |
| `frappe-code-review` | not installed | Same as above. Section 3 applies instead. |
| `frappe-ui` | does not exist | No such skill in frappe/skills. For `frontend/`, use https://github.com/frappe/frappe-ui (documentation and source). |

When an official skill becomes installable under a license, install it, load it, and stop using its substitute for
new tasks.

## 2. Approved substitutes

There are two kinds of substitute:

- A **skill substitute** is a local skill. The agent loads it with the Skill tool.
- A **procedure substitute** is a written procedure in this file. The agent runs it as written.

| Official skill | Substitute | Kind | SKILL.md SHA-256 | Scope | Approved | Re-check by |
|---|---|---|---|---|---|---|
| `frappe-app-dev` | `frappe-framework` (local) | skill | `c0460508f20044cbe356ac30e75c71c573dcc7f8a6583dd27ea217d105e2d949` | Frappe app code: DocTypes, controllers, hooks, permissions, APIs, reports, patches, fixtures, tests | Owner in principle 2026-11-02; final on merge | 2027-01-31 |
| `frappe-app-dev` (ERPNext/HRMS integration part) | `erpnext-platform` (local) | skill | `826773367ae2665b939f709a83e15a6c1b779689276a3566d5a158b182b4eb2d` | Use of standard ERPNext/HRMS documents and mechanisms | Owner in principle 2026-11-02; final on merge | 2027-01-31 |
| `frappe-app-dev` (frontend part) | `frappe-framework` (local) for server calls, plus the frappe-ui documentation and source (https://github.com/frappe/frappe-ui) for `frontend/` | skill | `c0460508f20044cbe356ac30e75c71c573dcc7f8a6583dd27ea217d105e2d949` | CARD Mobile (`frontend/`) | Owner in principle 2026-11-02; final on merge | 2027-01-31 |
| `frappe-code-review` | Review procedure in section 3 | procedure | — | Every code review | Owner in principle 2026-11-02; final on merge | 2027-01-31 |

Other local skills may be loaded as additional guidance when they apply (for example `frappe-bench-ops` for bench and
site operations, `erpnext-hrms-functional` for functional HR and accounting questions). They are not substitutes and
do not replace any official skill.

A substitute is valid only while all of these are true:

1. A skill substitute is loaded with the Skill tool in the task. A procedure substitute is run completely, as
   section 3 says.
2. A skill substitute requires official Frappe, ERPNext or HRMS sources only.
3. Before it loads a skill substitute, the agent computes the SHA-256 of its `SKILL.md`, compares it with the table
   and records it under `SKILLS_LOADED`. If the values differ, the agent stops and the row is re-approved first.
4. The task is inside the row's scope.
5. The re-check date has not passed.

The agent records each use as `SKILL SUBSTITUTE: <official> -> <substitute>`, for example
`SKILL SUBSTITUTE: frappe-code-review -> review procedure (section 3)`.

## 3. Review procedure (replaces `frappe-code-review`)

This procedure is mandatory for every change when `frappe-code-review` is not available.

1. **Independent reviewer.** A reviewer that did not write the change reviews the complete diff: a separate agent
   that gets the diff and this checklist, not the author's conclusions, or a human reviewer.
2. **Checklist.** The reviewer answers each item with "pass", "finding" or "not applicable". Each finding has a file
   and a line. Each "not applicable" has a one-line reason.
   1. Correctness: the change does what the task states, including edge cases (empty values, zero, boundaries,
      legacy records).
   2. Permissions: every `@frappe.whitelist` declares `methods=` and checks permission on the server; no new
      `ignore_permissions` without a written reason and its own check; cross-company access stays denied.
   3. Security: no secrets, hosts, user names, customer data or real company data in the diff; no new guest access
      (`allow_guest`) without the owner's decision; no unsafe HTML or script injection in Desk or `frontend/`; private
      files stay private.
   4. Data safety: no raw SQL with interpolated input; no write in a GET method; no silent data loss or
      redistribution.
   5. Accounting: CARD writes no GL entries; allocations sum exactly; posted documents stay unchanged.
   6. Schema and data: DocType and fixture changes are backward compatible; patches are idempotent; the rollback
      limits are written in CHANGELOG.md.
   7. Concurrency: checks that depend on other rows hold a lock or are safe under parallel saves.
   8. Performance: no query per row in loops over large sets without need.
   9. Translations: new user-facing strings are translated in every CARD locale file and are not generic msgids.
   10. Tests: new behaviour, edge cases and regressions have tests; existing tests are not weakened.
   11. Documentation: CHANGELOG.md and FEATURE-REGISTRY.md are updated as AGENTS.md requires.
3. **Findings.** The reviewer's output goes into the task checkpoint without edits. Each finding is fixed and
   re-checked by the reviewer, or the owner accepts it explicitly. The author does not mark a finding as fixed
   without that re-check.
4. **Security review.** When a change touches permissions, endpoints, secrets or data handling, the separate
   security review of the policy ([CHANGE-VERSIONING-ROLLBACK-POLICY.md](CHANGE-VERSIONING-ROLLBACK-POLICY.md),
   section 6) is still required. This procedure does not replace it.
5. **Gates stay.** The CI commands in AGENTS.md run before a push is requested. The approval ladder does not change.

This checklist is written for this repository. It does not copy or reproduce the content of `frappe-code-review`.

## 4. Changing this register

A new row, a changed hash or a changed scope needs the owner's approval in a documentation change (docs branch,
commit, push, pull request and merge, each approved). An agent never approves a substitute.
