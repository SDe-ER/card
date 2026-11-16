# CARD autonomous development policy

Canonical authorization document for the CARD project (repository `SDe-ER/card`).

- **Authorized by:** the project owner, 2026-11-16 (full autonomous project execution).
- **Scope:** every routine development task, including GitHub Issues and Pull Requests, code, bug fixes, enhancements,
  dependency updates, tests, database migrations written as code, documentation, screenshots, semantic versions, GitHub
  Releases and tags, CI/CD maintenance, production deployment of validated releases, post-deployment verification, and
  rollback of failed releases.
- **Not changed by this document:** the rules below in section 1.

## 1. What this document cannot change

This document records the owner's authorization. It does not override anything that is enforced outside the repository:

1. **Platform permissions.** Claude Code's permission system, its prompts and its denials still apply. A repository file
   cannot grant a tool permission that the platform has not granted. When the platform asks for approval, the agent asks.
2. **GitHub branch protection and required checks.** Changes reach `main` through pull requests, and only when the
   required checks pass on the exact head commit. Required checks are never disabled or bypassed.
3. **Security controls.** Gitleaks, Semgrep, CodeQL and Trivy stay required where CI defines them. Secrets are never
   committed, printed or pasted.
4. **Legally required approvals** of the company (for example tax filings and statutory accounts). Nothing in this
   document authorizes an action that law or company governance reserves to people.
5. **Infrastructure rules:** no work on the QA or development environments except as the QA constraints in `AGENTS.md`
   allow; Production SSH from the main session only; nothing written to drive C:.

## 2. Routine work (no per-task owner approval)

The agent may, without asking the owner for each task:

- open, triage, label and link GitHub Issues, and close an Issue only after verifying that it is resolved (never to
  reduce the count);
- create branches (`feat/`, `fix/`, `docs/`, `chore/`), commit, push and open pull requests;
- review and merge a pull request when section 3 is satisfied;
- create or change tests, migrations written as code, fixtures and documentation;
- update dependencies and CI workflows, keeping the minimum permissions in each workflow;
- update the semantic version (section 5), the CHANGELOG, the feature registry and the documentation site;
- create a Git tag and a GitHub Release for a validated version, and publish it;
- deploy a validated release to Production when section 4 is satisfied, verify it, and roll back if it fails.

## 3. Merging a pull request

A pull request is merged only when all of the following hold on the exact head commit:

1. Every required CI check passes (tests, linting, security scans, CodeQL, documentation build).
2. `/code-review` and `/security-review` report no HIGH or MEDIUM finding, or each finding is fixed and re-reviewed.
3. The CHANGELOG, the feature registry and the affected documentation pages are updated.
4. Migrations, if any, are reviewed for destructive operations and are idempotent.
5. The merge uses the exact head SHA (`--match-head-commit`), and the branch is not behind a protected base.

Commits are never rewritten after publication. Fixes are new commits. Tags are never moved or deleted.

## 4. Production deployment

A validated release is deployed to Production only when **all** of these hold. If any cannot be demonstrated, the agent
records the blocker in `docs/development-progress.md` and continues with independent work:

1. Tests and required CI checks pass on the release commit.
2. Frappe and ERPNext compatibility is verified against the platform actually running in Production (the running
   image and its installed versions, read-only).
3. A recoverable backup of the database and files is created and verified (archive integrity, table count, checksums).
4. Database migrations are validated: run twice, the second run changes nothing; no destructive operation without a
   reviewed plan.
5. Accounting consistency is checked before and after: submitted-document amounts, GL and payment ledger totals, and
   ZATCA state are unchanged except for the documented changes. Any unexplained difference stops the deployment.
6. A rollback target and procedure are written before the change (the last known-good image and commit, and the steps).
7. The validated release is deployed.
8. Production smoke tests pass (health, login, key pages, asset URLs, the features the release changes).
9. Failures are monitored; a failed release is rolled back automatically when the rollback is supported and the
   database state permits it. A database restore is never automatic.

Never bypass a security restriction, disable a required check, or run an unverified destructive operation. Never create
or change accounting entries from the application outside the ERPNext documents CARD already creates.

## 5. Semantic versioning

- **PATCH** (4.9.0 → 4.9.1): bug fixes, security patches and backward-compatible maintenance.
- **MINOR** (4.9.1 → 4.10.0): backward-compatible functionality.
- **MAJOR** (4.10.0 → 5.0.0): breaking API, schema or behaviour changes. **A MAJOR release is not published without a
  separate written owner decision.**

Each release: version in `card/__init__.py`, a `[X.Y.Z]` CHANGELOG section, the release page under `docs/releases/`,
the version table, the release notes (EN and AR), and a Git tag matching the version. A release is not published for
every commit; related changes are grouped into a small, independently verified release.

## 6. Documentation and screenshots

Every user-visible change updates the affected documentation page (EN and AR) and the What's new entry. Screenshots are
taken only from a working application environment that the rules allow, and show fictitious data. A mockup is never
presented as a screenshot. When a screenshot cannot be captured, the page says so and the item stays open.

## 7. Progress and resumption

- `docs/development-progress.md` is the human-readable checkpoint.
- `.claude/card-progress.json` is the machine-readable checkpoint. The `.claude` folder is git-ignored in this
  repository, so this file is kept locally and is not committed.
- At the start of every session the agent reads the checkpoint, refreshes the live GitHub backlog, verifies the last
  completed step against GitHub and the running system, and resumes the highest-priority unblocked task.

## 8. Blockers

A blocker is recorded with its exact cause, the step that stopped, and the next independent task. Blockers are not
closed by workarounds. A blocker that needs a credential, a permission that has not been granted, or a legal decision
is reported to the owner in the progress file.

## 9. Relation to other documents

This document governs routine execution. Where `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, the release policy or the
change-versioning policy require an owner approval for a routine step, this document supersedes that requirement for
that step. Their safety requirements, technical rules and rollback rules remain in force.
