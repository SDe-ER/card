---
title: Development and contributing
description: How to run CARD's tests, the checks every pull request runs, how releases are made, and how to keep this documentation up to date.
sidebar:
  order: 4
---

## Overview

CARD is developed in the open on [GitHub](https://github.com/SDe-ER/card). Every change goes through a pull
request with automated checks and review. This page explains how to run the tests locally, which checks a pull
request runs, how versions are released, and how each change reaches this documentation.

## Run the tests

Run the tests on a development or test site only, never on a production site:

```bash
bench --site <dev-site> set-config developer_mode 1
bench --site <dev-site> set-config allow_tests true
bench --site <dev-site> run-tests --app card
```

The same commands that CI runs:

```bash
pre-commit run --all-files
cd frontend && yarn install --frozen-lockfile && yarn type-check && yarn test && yarn build
```

## Checks on every pull request

| Workflow | What it checks |
|---|---|
| CI | CARD unit tests on Frappe and ERPNext v16 with coverage; CARD Mobile type check, unit tests and build |
| Linters | `pre-commit` (ruff, prettier) and Semgrep with the Frappe rules |
| CodeQL | Code scanning for JavaScript and Python, also weekly |
| PR Title | The pull request title follows Conventional Commits |
| Upgrade rehearsal | An upgrade from an earlier release, when patches, DocTypes, fixtures or hooks change |
| Docs site | Builds this site; on `main` it also publishes it |
| Release | Makes the GitHub Release when a `v*` tag is pushed |

## Contributing

1. Open an issue that describes the change.
2. Work on a `feat/`, `fix/` or `docs/` branch, never on `main`.
3. Add or update tests and keep `pre-commit` green.
4. Record the change in `CHANGELOG.md` under `[Unreleased]` and in the feature registry.
5. Add the change to [What's new](/card/releases/whats-new/) in English and Arabic (see below).
6. Open a pull request with a [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) title.

Each step of the way to production needs its own approval: a commit is not a push, a merge is not a release, and
a release is not a deployment. See [CONTRIBUTING.md](https://github.com/SDe-ER/card/blob/main/CONTRIBUTING.md),
the [code of conduct](https://github.com/SDe-ER/card/blob/main/CODE_OF_CONDUCT.md) and the
[change, version and rollback policy](https://github.com/SDe-ER/card/blob/main/docs/governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md).

## Keep this documentation up to date

The site lives in the `website/` folder of the repository and is rebuilt and published automatically from
`main` whenever the CARD code or the documentation changes.

| When you change… | Update |
|---|---|
| Anything users or administrators notice | Add an entry to [What's new](/card/releases/whats-new/) in English (`website/src/content/docs/releases/whats-new.md`) and Arabic (`website/src/content/docs/ar/releases/whats-new.md`) |
| A DocType, field, report or whitelisted method | Run `cd website && npm run generate` and commit the regenerated [Reference](/card/reference/) pages |
| How a feature behaves | Its page under `website/src/content/docs/` and its Arabic copy under `.../ar/` |
| A screen that has a screenshot | Re-capture it from the demo site with `website/scripts/screenshots/` (invented data only) |

Writing rules for every page are in
[`website/WRITING-GUIDE.md`](https://github.com/SDe-ER/card/blob/main/website/WRITING-GUIDE.md). To preview the
site locally:

```bash
cd website
npm ci
npm run dev
```

## Releases

CARD follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Every release has its own release
notes, and every version is listed on [What's new](/card/releases/whats-new/).

## Security

Report vulnerabilities privately as described in
[SECURITY.md](https://github.com/SDe-ER/card/blob/main/SECURITY.md). Do not open public issues for them.

## Related

- [Installation](/card/getting-started/installation/)
- [Roles and permissions](/card/features/roles-permissions/)
- [What's new](/card/releases/whats-new/)
