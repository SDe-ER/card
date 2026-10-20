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
- Before relying on the "last recorded state" for a deployment or a rollback, re-verify it on the site.

## Last recorded state

This table repeats the last recorded evidence. It is **not** a live check of what runs today.

| Environment | Version | Tag | Commit | Deployed | Evidence |
|---|---|---|---|---|---|
| Production | v1.0.1 | `v1.0.1` | `8118c6f` | 2026-10-13 | Last operational evidence dated 2026-10-13 (post-deployment checks, private operations record). No later direct verification is recorded here; re-verify on the site before relying on it |

## Reference versions

These three are different facts and are never inferred from each other:

| Term | Value | Basis |
|---|---|---|
| **Last GitHub Release** | v4.0.0 (`2dd5b77`, 2026-10-19) | Git tag and GitHub Release. A release is not a deployment: no Production deployment of v4.0.0 is recorded |
| **Last Verified Production Deployment** | v1.0.1 (`8118c6f`), deployed 2026-10-13 | Post-deployment checks dated 2026-10-13. This is the last evidence, not a check of the current state |
| **Last Known Good Release** | Not established | No release has a recorded known-good acceptance (a verified deployment plus a documented period of correct operation). Set it only when that evidence is recorded |

Releases with no recorded Production deployment: v1.2.0, v1.2.1, v1.2.2, v3.0.0, v4.0.0.

## History

| Date | Environment | Change | From → To | Evidence |
|---|---|---|---|---|
| 2026-10-13 | Production | Hotfix deployment (Frappe 16.50/16.51 migrate compatibility) | earlier state not recorded here → v1.0.1 | Verified by post-deployment checks on 2026-10-13 (private operations record) |
