# CARD Change, Versioning & Safe Rollback Policy

**Status: binding** for every change to CARD: Desk, backend, reports, fixtures, patches and CARD Mobile.
Adopted 2026-10-20 by the project owner.

This policy ties together the rules that already exist and adds what was missing. It does not repeat them:

| Topic | Where the detailed rule lives |
|---|---|
| Release checklist, truthfulness labels, immutable release history | [docs/releases/RELEASE-POLICY.md](../releases/RELEASE-POLICY.md) |
| Feature registry rules and status values | [FEATURE-REGISTRY.md](FEATURE-REGISTRY.md#rules) |
| Pull request rules, tests, linting | [CONTRIBUTING.md](../../CONTRIBUTING.md) |
| Which version runs where | [docs/releases/DEPLOYMENTS.md](../releases/DEPLOYMENTS.md) |

If two documents disagree, this policy wins for change, version and rollback questions. Report the conflict and
fix the other document in its own change.

## 1. Changes and commits

- Every change has its own clear commit (Conventional Commits). Independent changes are never mixed in one commit or
  one pull request.
- A change is committed once the owner has approved that task. An agent never commits on its own initiative.
- Published history is never rewritten: no force-push to a shared branch, no amended or rebased published commits,
  no moved, renamed or deleted tags. A mistake is fixed with a new commit (for example `git revert`).

## 2. CHANGELOG

- Every change that affects behaviour, data, permissions, accounting, an API, a schema, fixtures or patches is
  recorded in [CHANGELOG.md](../../CHANGELOG.md) under `[Unreleased]` (or the target version's section) in the same
  pull request. Documentation-only and test-only changes are recorded when they change a rule, a policy or what is
  proven.
- Use the Keep a Changelog headings: **Added**, **Changed**, **Fixed**, **Removed**, **Security** (and the release
  headings listed in RELEASE-POLICY.md).
- Each entry states:
  - what changed and why;
  - the affected functions, DocTypes or endpoints;
  - the issue, pull request or commit;
  - the impact on permissions, accounting, data and the API (write "none" when there is none);
  - compatibility and rollback limits (for example "needs a data patch; rolling back the code does not undo it").
- No release with an undocumented change. Before a release, compare the commits since the previous tag with the
  CHANGELOG section; every merged pull request must appear or be listed as having no user impact.

## 3. Feature Registry

- [FEATURE-REGISTRY.md](FEATURE-REGISTRY.md) is updated in the same task whenever a feature is added, fixed,
  changed, disabled or removed. Its own rules apply (stable `FR-NNN` IDs, no deleted rows, evidence column).
- Keep the statuses apart, each with its proof: planned, in review, implemented (merged and tested), released
  (tagged), deployed (verified on the site). A plan is not an implementation; a merge is not a release; a release is
  not a deployment.

## 4. Versions and releases

- Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) as documented in CHANGELOG.md. Past
  tags and releases stay as published (including the jump from 1.2.2 to 3.0.0); no retroactive release, tag rename
  or re-tag.
- Every pull request states its **target version** (or "next release" while unreleased). The version number in
  `card/__init__.py` changes only in the release pull request.
- A release needs all of:
  1. a fixed SemVer tag `vX.Y.Z` on a commit of `main`;
  2. CHANGELOG and Feature Registry in agreement;
  3. green CI, tests and security review on the tagged commit;
  4. migration, schema and fixture changes documented (what `migrate` writes and does not write);
  5. a comparison with the previous release (RELEASE-POLICY.md checklist);
  6. a rollback statement (section 5).
- A pull request or a commit is not a release. A release is not a Production deployment. Each deployment is
  recorded per environment in [DEPLOYMENTS.md](../releases/DEPLOYMENTS.md) with its evidence.

## 5. Safe rollback

Before any deployment, write down:

1. the rollback target: the Last Known Good Release, or, while none is established, the Last Verified Production
   Deployment, with its tag and commit (terms defined in DEPLOYMENTS.md; never assume a release was deployed);
2. what currently runs on Production (from DEPLOYMENTS.md, re-verified on the site, since that file records the last
   evidence, not a live check);
3. every change between the two (CHANGELOG sections and merged pull requests);
4. the rollback steps.

Rules:

- A verified backup (database and files, restore tested or at least checked for completeness) is taken before every
  deployment.
- Checking out an old tag restores **code only**. It never restores the database. A change that adds or changes a
  DocType, fixtures, patches, migrations or accounting documents needs, before deployment, a written plan that says
  whether the old code can run on the new data, and either how to restore safely or how to fix forward.
- A restore that would lose transactions made on Production after the backup is not allowed. In that case the
  rollback is a forward fix.
- No actual rollback, restore or downgrade without the owner's explicit approval for that action.

## 6. Closing a task

A task is closed only when:

1. every operation it started has finished and its result is checked;
2. the diff is reviewed (code review, plus security review when permissions, endpoints, secrets or data handling are
   touched);
3. CHANGELOG and Feature Registry are updated, or the reason they are not is written down;
4. the evidence (test output, CI links, hashes) is kept;
5. a full checkpoint is written in the maintainers' private records: objective and status, files, tests, evidence,
   decisions and approvals, open points, next step.

Then the agent reports that it is ready for context compaction. Only the owner runs it; an agent never starts it.

## 7. Approval ladder

Each step needs its own explicit approval from the owner; an approval for one step never covers the next:

```
local commit  ≠  push  ≠  merge  ≠  tag / release  ≠  deploy  ≠  rollback
```

A Production deployment or rollback always needs a separate, explicit approval naming that action, after the
backup and the rollback plan in section 5.

## 8. Agents

AI agents working on this repository read this file through [AGENTS.md](../../AGENTS.md) at the repository root.
Maintainers' private rules (hosts, sites, credentials handling) are kept outside this public repository and add to
this policy; they never weaken it.
