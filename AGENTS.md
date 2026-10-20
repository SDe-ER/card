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
