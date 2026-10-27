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
| Production | v4.2.2 | `v4.2.2` | `54f53f2` | 2026-10-27 (UTC) | Verified by post-deployment checks on 2026-10-27 (UTC) (private operations record). Re-verify on the site before relying on it |

## Reference versions

These three are different facts and are never inferred from each other:

| Term | Value | Basis |
|---|---|---|
| **Last GitHub Release** | v4.2.2 (`54f53f2`, 2026-10-27) | Git tag and GitHub Release |
| **Last Verified Production Deployment** | v4.2.2 (`54f53f2`), deployed 2026-10-27 (UTC) | Post-deployment checks dated 2026-10-27 (UTC). This is the last evidence, not a check of the current state |
| **Last Known Good Release** | Not established | No release has a recorded known-good acceptance (a verified deployment plus a documented period of correct operation). Set it only when that evidence is recorded |

Releases with no recorded Production deployment: v1.2.0, v1.2.1, v1.2.2, v3.0.0, v4.0.0, v4.1.0. v4.1.1 ran on
Production (observed 2026-10-25), but its deployment was not recorded here when it happened.

## History

| Date | Environment | Change | From → To | Evidence |
|---|---|---|---|---|
| 2026-10-13 | Production | Hotfix deployment (Frappe 16.50/16.51 migrate compatibility) | earlier state not recorded here → v1.0.1 | Verified by post-deployment checks on 2026-10-13 (private operations record) |
| 2026-10-25 | Production | Late record: v4.1.1 observed running before the v4.1.2 deployment (its own deployment was not recorded here) | v1.0.1 (last recorded) → v4.1.1 | Observed on the site on 2026-10-25 (UTC) during the v4.1.2 pre-deployment checks (private operations record) |
| 2026-10-25 | Production | Upgrade to v4.1.2 (no new patch; `after_migrate` restores the launcher entries; CARD translations compiled into the image) | v4.1.1 → v4.1.2 | Verified by post-deployment checks on 2026-10-25 (UTC): version and image, migrate run twice with no change on the second run, launcher entries, service health, data unchanged (private operations record) |
| 2026-10-27 | Production | Upgrade to v4.2.0 (patch `v4_1_3.remove_app_name_translations`; DocType sync: diesel session evidence columns, child table `Diesel Fill Equipment`, fitment columns) | v4.1.2 → v4.2.0 | Verified by post-deployment checks on 2026-10-27 (UTC): version and image, migrate run twice with no change on the second run, new columns and child table present, diesel fill form opens, data unchanged apart from the patched Translation row (private operations record) |
| 2026-10-27 | Production | Upgrade to v4.2.1 (no patch, no column; diesel fill form layout) | v4.2.0 → v4.2.1 | Verified by post-deployment checks on 2026-10-27 (UTC): version and image, migrate run twice, data unchanged, new diesel fill form opens (private operations record) |
| 2026-10-27 | Production | Upgrade to v4.2.2 (no patch, no column, no DocType change; diesel meter photos shown large on the fill form, Arabic reading labels) | v4.2.1 → v4.2.2 | Verified by post-deployment checks on 2026-10-27 (UTC): version and image, migrate run twice, data unchanged, a fill shows both meter photos as cards with the new labels (private operations record) |
