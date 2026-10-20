# CARD — Deployment Record

Which CARD version runs in each environment. Required by the
[Change, Versioning & Safe Rollback Policy](../governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md).

> **Published ≠ deployed.** [VERSION-HISTORY.md](VERSION-HISTORY.md) lists published releases. This file lists
> deployments only. This repository is public: it records versions, tags, commits and dates only. Hosts, sites,
> users and operational logs stay in the maintainers' private records.

Rules:

- Add a row to the history for every deployment, upgrade or rollback, in the same week it happens. Never edit or
  delete an older row; correct it with a new dated row.
- A row states the evidence level: **Verified** (checked on the site after the deployment, with a private record
  reference) or **Unverified**.
- Before relying on the "current" table for a deployment or a rollback, re-verify it on the site.

## Current state

| Environment | Version | Tag | Commit | Deployed | Evidence |
|---|---|---|---|---|---|
| Production | v1.0.1 | `v1.0.1` | `8118c6f` | 2026-10-13 | Verified on the site after deployment (private operations record, 2026-10-13). Re-verify before the next deployment |

## Stable versions

- **Last published release:** v4.0.0 (`2dd5b77`, 2026-10-19). Not deployed to Production.
- **Last stable version running on Production:** v1.0.1 (`8118c6f`).
- Releases published but never deployed to Production: v1.2.0, v1.2.1, v1.2.2, v3.0.0, v4.0.0.

## History

| Date | Environment | Change | From → To | Evidence |
|---|---|---|---|---|
| 2026-10-13 | Production | Hotfix deployment (Frappe 16.50/16.51 migrate compatibility) | earlier state not recorded here → v1.0.1 | Verified (private operations record) |
