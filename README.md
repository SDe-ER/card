<div align="center">

<img src="card/public/images/card-logo.svg" alt="CARD application logo" height="92">

# CARD

**Equipment operations, rentals and monthly cards for ERPNext**

**إدارة المعدات والإيجارات وكروت التشغيل الشهرية**

[![CI](https://github.com/SDe-ER/card/actions/workflows/ci.yml/badge.svg)](https://github.com/SDe-ER/card/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/SDe-ER/card?label=release)](https://github.com/SDe-ER/card/releases)
![Frappe v16](https://img.shields.io/badge/Frappe-v16-blue)
[![MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**[Documentation portal source](https://github.com/SDe-ER/card-docs)** · **[Releases](https://github.com/SDe-ER/card/releases)** · **[Changelog](CHANGELOG.md)** · **[Report an issue](https://github.com/SDe-ER/card/issues)**

<img src=".github/images/card-landing.png" alt="CARD workspace using fictional demonstration data" width="90%">

</div>

> [!IMPORTANT]
> **Release is not deployment.** A GitHub release does not establish what is installed on any ERPNext site. Verify the site's installed app version and deployed commit before upgrading. Features on `main` may not be included in the latest release.

## Overview

CARD is a standalone [Frappe Framework](https://frappeframework.com) application integrated with ERPNext for contractors managing owned and rented heavy equipment. It connects equipment, project assignments, daily operating hours, supplier costs, customer revenue and accounting-ready records without maintaining a separate general ledger.

**Who it serves:** equipment operators, project teams, procurement, commercial teams and accountants. **Where it runs:** a compatible Frappe/ERPNext v16 bench.

## Explore CARD

| Area | What it does | Guide |
| --- | --- | --- |
| Equipment | Owned/rented equipment, types, categories, rental direction and standard hours | [Equipment guide](https://github.com/SDe-ER/card-docs/blob/main/docs/en/user-guide/equipment.md) |
| Assignments | Equipment-to-project/site assignments with date ranges and overlap controls | [Documentation index](https://github.com/SDe-ER/card-docs) |
| Monthly cards | Day status, operating hours, additions, deductions and supplier/customer amounts | [Monthly cards](https://github.com/SDe-ER/card-docs/blob/main/docs/en/user-guide/monthly-cards.md) |
| Suppliers & customers | Party registries, statements and summary reports | [Supplier guide](https://github.com/SDe-ER/card-docs/blob/main/docs/en/user-guide/suppliers.md) |
| Diesel & transport | Project fills, allocation analysis, transport pricing and operational reporting | [Diesel analysis](https://github.com/SDe-ER/card-docs/blob/main/docs/en/reports/diesel-analysis.md) |
| Accounting | Equipment dimension, guard reports and **opt-in** draft invoice generation for accountant review | [Monthly posting](https://github.com/SDe-ER/card-docs/blob/main/docs/en/accounting/monthly-posting.md) |
| Administration | Per-company settings, roles, reporting access and period controls | [Card Settings](https://github.com/SDe-ER/card-docs/blob/main/docs/en/administration/card-settings.md) |

<div align="center">
<img src=".github/images/card-equipment.png" alt="Equipment master" width="46%">
<img src=".github/images/card-monthly-card.png" alt="Monthly operation card" width="46%">
</div>

### How the workflow fits together

```text
Equipment master → Project assignment → Monthly operation card
                                            ├─ Supplier costs / statements
                                            ├─ Customer revenue / statements
                                            └─ Optional draft ERPNext invoices → Accountant review
Diesel fills / transport ──────────────────→ Project and equipment cost analysis
```

### Billing, in brief

Both supplier and customer billing use **recorded operating hours**, with three supported rate bases:

| Rate basis | Effective hourly rate |
| --- | --- |
| Hourly | `rate` |
| Daily | `rate / standard_daily_hours` |
| Monthly | `rate / standard_month_hours` |

`amount = total_operating_hours × effective_hourly_rate`

`net = amount + applicable_additions − applicable_deductions`

For example, a daily rate of 600 with a 10-hour standard day and 88 actual hours yields **5,280** before applicable adjustments and tax. **Daily-rate billing is hours-prorated, not full-day billing.** Supplier and customer adjustments are calculated separately.

## Release and feature status

| Status | Meaning |
| --- | --- |
| **Released** | Included in a published, tagged CARD release; not proof of production deployment |
| **Main only** | Merged into `main`, but not part of the latest release |
| **In development** | Being built or reviewed; not shipped |
| **Design only** | Proposed or approved architecture, not implemented |

Use the [release notes](https://github.com/SDe-ER/card/releases), [CHANGELOG](CHANGELOG.md) and the [version-aware documentation source](https://github.com/SDe-ER/card-docs) together. Do not interpret future design pages as available features.

> [!WARNING]
> **Known limitations:** Multi-company supplier/customer registry totals are not fully isolated ([#23](https://github.com/SDe-ER/card/issues/23)). The pre-VAT card-to-VAT-inclusive-GL reconciliation difference also requires attention. See the [v1.2.1 changelog](CHANGELOG.md#121--2026-10-16) and open issues before multi-company or accounting use. Accounting posting is disabled until explicitly configured per company; generated invoices are drafts, not submitted invoices.

## Requirements and compatibility

| Component | Supported/tested reference |
| --- | --- |
| Frappe Framework | v16; tested with 16.51.1 |
| ERPNext | v16; tested with 16.50.0 |
| Frappe HR | Optional; tested with 16.50.0 |
| Runtime used in tests | Python 3.14, Node.js 24, MariaDB 10.6, Redis |

The exact compatible versions and migration requirements depend on the release. Check the [release notes](https://github.com/SDe-ER/card/releases) before installation.

## Installation and upgrade

**For a reproducible release installation**, use a specific reviewed tag rather than tracking `main`:

```bash
cd frappe-bench
bench get-app https://github.com/SDe-ER/card --branch v1.2.1
bench --site your-site.local install-app card
```

The installation command is for a **new development/test site**, not an instruction to upgrade production. For an existing site, take a full backup, rehearse migration on a restored copy, verify the exact target commit and follow the [upgrade guide](https://github.com/SDe-ER/card-docs/blob/main/docs/en/deployment/upgrade.md). Docker installations require a custom image containing CARD; see the documentation and your deployment procedure.

**Developer checkout:** `bench get-app https://github.com/SDe-ER/card --branch main` is for development, not a pinned production release.

## Development and quality

```bash
bench --site card.localhost set-config allow_tests true
bench --site card.localhost run-tests --app card
pre-commit run --all-files
```

Use a configured **non-production** development site. Follow [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, PR conventions, code review and CI. Do not change Frappe/ERPNext core; business rules belong in the app's server-side code.

## Documentation

The **application source of truth** lives here in `SDe-ER/card`; the **documentation source of truth** lives in **[SDe-ER/card-docs](https://github.com/SDe-ER/card-docs)**.

- [English documentation index](https://github.com/SDe-ER/card-docs/blob/main/docs/en/index.md) · [فهرس التوثيق العربي](https://github.com/SDe-ER/card-docs/blob/main/docs/ar/index.md)
- [Installation](https://github.com/SDe-ER/card-docs/blob/main/docs/en/getting-started/install.md) · [Administration](https://github.com/SDe-ER/card-docs/blob/main/docs/en/administration/card-settings.md) · [Accounting](https://github.com/SDe-ER/card-docs/blob/main/docs/en/accounting/monthly-posting.md)
- [Reports](https://github.com/SDe-ER/card-docs/tree/main/docs/en/reports) · [API](https://github.com/SDe-ER/card-docs/blob/main/docs/en/api/posting-endpoints.md) · [Troubleshooting](https://github.com/SDe-ER/card-docs/blob/main/docs/en/troubleshooting/posting-refusals.md)

The documentation portal's publication is independently controlled. These source links work without assuming a public website is deployed or available.

## Project information

| Resource | Link |
| --- | --- |
| Release history | [Releases](https://github.com/SDe-ER/card/releases) / [CHANGELOG](CHANGELOG.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Code of conduct | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |
| Security reports | [SECURITY.md](SECURITY.md) — private disclosure to **info@sdce.sa** |
| License | [MIT](LICENSE) |
| Documentation contributions | [card-docs/CONTRIBUTING.md](https://github.com/SDe-ER/card-docs/blob/main/CONTRIBUTING.md) |

CARD is an independent product of **Shams Dubai Contracting Est. (SDCE)**, not developed, endorsed or maintained by Frappe Technologies. Frappe, ERPNext and Frappe HR names are used solely to describe compatibility. CARD branding belongs to SDCE.

<div align="center"><sub>Illustrations and screenshots use fictional demonstration data.</sub></div>
