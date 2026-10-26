# AGENTS.md — CARD

Rules for every AI coding agent (Claude Code, Codex and others) working in this repository. Format:
https://agents.md. Maintainers may keep stricter private rules outside this public repository; when two rules
differ, the stricter one applies.

## Read first

- [docs/governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md](docs/governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md) —
  binding policy for changes, versions, releases, deployments and rollback.
- [CONTRIBUTING.md](CONTRIBUTING.md) — branches, tests, linting, pull requests.
- [docs/governance/FEATURE-REGISTRY.md](docs/governance/FEATURE-REGISTRY.md) — what exists and how it is proven.
- [docs/releases/RELEASE-POLICY.md](docs/releases/RELEASE-POLICY.md) — release checklist.

## Go-live priority (issue #118)

Issue #118 is the owner's go-live plan and sets the order of release work: #119 (P0 readiness) → #120 (P1 equipment)
→ #121 (P2 transport) → #122 (P3 project assignment) → #123 … #127. It adds to the rules in this file and the policy
above; it removes none of them.

- Work on the current phase only. Earlier requirements stay recorded, but an optional improvement never blocks a
  release: record it in the backlog, link it to the phase, and continue.
- Each phase: check what exists → list the production blockers only → fix them → test → ask for the production
  approval → deploy → check the real use. Do not rebuild what already works or repeat a check that passed on the
  same code and environment without a stated reason.
- CI, a merge or a QA pass is not LIVE. Close a phase only after its acceptance criteria pass in real use, with
  evidence and the owner's approval.

## Skills (before every task)

Agents that have a Skill tool follow these rules for every development or review task:

1. Choose the official Frappe skills that fit the task (from https://github.com/frappe/skills), for example
   `frappe-app-dev` for app code or `frappe-code-review` for a review.
2. Load each one with the Skill tool. Reading a `SKILL.md` file does not load the skill.
3. For CARD Mobile (`frontend/`), also load the official `frappe-ui` skill.
4. Also load the maintainer's local SDCE skills (`sdce-*`) that apply to the task.
5. If a required skill is not available, record `SKILL NOT FOUND: <name>` and stop.
6. List each loaded skill under `SKILLS_LOADED` in the task report and checkpoint: name, official or local, how it
   was loaded, purpose and result. Write `SKILLS_LOADED=none` when no skill was loaded. Never list a skill that was
   not loaded.

The maintainer's private rules (`../../AGENTS.md` from the repository root, section 8) give the details. This
section applies also when that file is not loaded.

## Approval ladder

Each step needs the owner's explicit approval for that step; one approval never covers the next:

```
local commit  ≠  push  ≠  merge  ≠  tag / release  ≠  deploy  ≠  rollback
```

- Commit only when the owner asked for it or the approved task includes committing. Use a `feat/`, `fix/` or
  `docs/` branch, never `main`; stage explicit paths only; one task per commit (Conventional Commits).
- Never rewrite published history: no force-push, no amending or rebasing published commits, no moving, renaming or
  deleting tags, no retroactive releases.
- Never deploy, migrate, restore or roll back any production site without a separate explicit approval for that
  action, a verified backup and the written rollback plan required by the policy.

## Every change

- Record it in `CHANGELOG.md` under `[Unreleased]` with its reason, the affected functions, its pull request or
  commit, its impact on permissions, accounting, data and the API, and its rollback limits.
- Update `docs/governance/FEATURE-REGISTRY.md` when a feature is added, fixed, changed, disabled or removed. A plan
  is not an implementation; a merge is not a release; a release is not a deployment.
- Add or update tests; run the CI commands below before asking for a push.
- Never commit secrets, hosts, user names, customer data or real company data.

## Engineering rules

- Standard Frappe/ERPNext mechanisms first; never edit Frappe, ERPNext or HRMS core.
- Depends on `frappe` and `erpnext` only.
- CARD never writes GL entries; it creates standard ERPNext documents.
- Multi-company: never hardcode a company, account, user or price; cross-company access is always denied on the
  server.
- Every `@frappe.whitelist` declares `methods=`: `["GET"]` only for reads without side effects, `["POST"]` for
  anything that writes.
- Do not widen roles or permissions, and do not use `ignore_permissions` to make something work.
- The app name is "Card" in every language; `card/locale/*.po` holds CARD strings only.

## CI commands (mirror `.github/workflows/`)

```bash
pre-commit run --all-files
cd frontend && yarn install --frozen-lockfile && yarn type-check && yarn test && yarn build
bench --site <dev-site> run-tests --app card   # development or test site only, never production
```
