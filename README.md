<div align="center">

<img src="card/public/images/card-logo.svg" alt="CARD logo" height="96">

<h1>CARD</h1>

**Equipment operations management for ERPNext**

إدارة تشغيل المعدات

[![CI](https://github.com/SDe-ER/card/actions/workflows/ci.yml/badge.svg)](https://github.com/SDe-ER/card/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/SDe-ER/card)](https://github.com/SDe-ER/card/releases/latest)
[![codecov](https://codecov.io/gh/SDe-ER/card/graph/badge.svg)](https://codecov.io/gh/SDe-ER/card)

</div>

CARD is a Frappe application for contractors that own, rent and operate heavy equipment. It tracks every
machine, where it works and who runs it, records its monthly operating hours, and turns them into supplier
and customer amounts on official ERPNext documents.

CARD is developed by **Shams Dubai Contracting Est. (SDCE)**, Saudi Arabia, for its mobile crushing,
infrastructure and equipment rental operations.

<div align="center">
<img src=".github/images/card-landing.png" alt="CARD in the ERPNext Desk" width="90%">
<br><sub>CARD in the ERPNext Desk (fictional demo data).</sub>
</div>

## Contents

- [Overview](#overview)
- [Features](#features)
- [CARD Mobile](#card-mobile)
- [Integration with Frappe, ERPNext and Frappe HR](#integration-with-frappe-erpnext-and-frappe-hr)
- [Requirements](#requirements)
- [Installation](#installation)
- [Development](#development)
- [Security and permissions](#security-and-permissions)
- [Languages](#languages)
- [Versions and releases](#versions-and-releases)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Overview

CARD has two interfaces on the same app and the same data:

| Interface | For | Status |
|---|---|---|
| **CARD Desk** | Managers, supervisors, accounts and stores, working in the ERPNext Desk | Available |
| **CARD Mobile** (`/cdms`) | Operators, supervisors and managers on site, on their phones | In v4.1.0, not yet tested on real phones (see [CARD Mobile](#card-mobile)) |

CARD Desk is the full management system. CARD Mobile is a phone front end for the few actions people need
on site; it does not duplicate the Desk.

CARD follows the design of Frappe HR: one master record per machine (like Employee), one transaction per
period (like Salary Slip), and every record linked to ERPNext's Company, Project, Supplier, Customer and
Asset.

## Features

Everything below is available in the latest release, **v4.1.0**. The complete inventory of each version is
in [docs/releases](docs/releases/VERSION-HISTORY.md).

### Equipment

- **Card Equipment** master with type, category, ownership (owned, managed or rented), supplier, company
  and documents with expiry warnings.
- Owned and managed equipment take their name, brand, type and details from the linked ERPNext **Asset**.
- Units made of several machines, with dated components.

### Movement and transport

- **Equipment Transport** moves one or more machines to a project, workshop, storage or back to the
  supplier. CARD reads where each machine is and charges the destination's cost center.
- Project assignments are created and closed by approved transports.

### Monthly operation cards

- **Card Monthly Card** per machine, shift and month, with a day-by-day grid of operating hours.
- The project comes from the machine's approved transports; no transport, no card.
- Hourly, daily and monthly rates on both the supplier (cost) and customer (revenue) side, with additions
  and deductions.

### Diesel, materials and custody

- Per-project diesel fills, diesel supplier policy and expected-versus-actual diesel analysis.
- **Equipment needs:** operators request parts, consumables and tools for their machine; the site
  supervisor reviews; management approval creates draft ERPNext **Material Requests**.
- Returnable tools tracked as employee custody.

### Accounting and reports

- Postings only through official ERPNext documents (Purchase Invoice, Sales Invoice, Material Request,
  Stock Entry). CARD never writes General Ledger entries directly.
- A **Card Equipment** accounting dimension for per-machine ledgers and financial statements.
- Period lock, company isolation and a permanent posting log.
- 13 reports, including supplier and customer statements, operating and transport cost by project, diesel,
  materials and custody.
- RTL Arabic print formats for the monthly card, diesel fill and transport.

## CARD Mobile

> [!IMPORTANT]
> **In v4.1.0, not yet tested on real phones.** v4.1.0 is the foundation of CARD Mobile (operator
> requests); the full phone app for CARD is planned from v4.2.0.

CARD Mobile is a Progressive Web App (PWA) served by CARD itself at `/cdms`, built the same way as the
Frappe HR mobile app:

- **Phone only.** One interface designed for phones. On a computer the same interface is shown in a
  centered column up to 480 px wide; there is no separate desktop layout.
- **Same accounts.** Users sign in inside the app with their ERPNext account. Sessions, CSRF protection
  and permissions are Frappe's own; the user needs a CARD role and an active Employee record.
- **No duplicate logic.** The app calls CARD's existing endpoints; CARD Desk stays the management system.
- **Installable.** Web app manifest, app icons and iPhone home-screen settings are included.

| Screen | For | Status |
|---|---|---|
| Sign in, Home, New request, My requests, Profile | Operators | In v4.1.0 (not device-tested) |
| Daily operating hours (enter, review, approve) | Operators, supervisors, managers | Planned |
| Equipment, projects, transport, cards, diesel | By role | Planned |
| Materials review and approval, tools and custody | Supervisors, managers, operators | Planned |
| Suppliers, costs, reports, notifications | By role | Planned |

> [!NOTE]
> iPhone (Safari → *Add to Home Screen*) and Android (*Install app*) installation has **not yet been
> tested on physical devices**. Support will be stated only after those tests on an HTTPS site.

Details: [docs/mobile](docs/mobile/README.md).

## Integration with Frappe, ERPNext and Frappe HR

| Application | How CARD uses it |
|---|---|
| [Frappe Framework](https://github.com/frappe/frappe) | DocTypes, permissions, sessions, translations, web pages |
| [ERPNext](https://github.com/frappe/erpnext) | Company, Project, Supplier, Customer, Asset, Item, Employee, Material Request, invoices and the General Ledger |
| [Frappe HR](https://github.com/frappe/hrms) | Optional. CARD uses ERPNext's Employee record, which Frappe HR extends |

CARD does not modify Frappe, ERPNext or Frappe HR. It extends them only through standard mechanisms
(hooks, custom DocTypes, accounting dimensions and permissions).

> CARD is an independent product of SDCE. It is not developed, endorsed or maintained by Frappe
> Technologies.

## Requirements

| Component | Version |
|---|---|
| Frappe Framework | 16.51 or later (v16) |
| ERPNext | v16 |
| Frappe HR | v16, optional |
| Python | 3.14 |
| Node.js | 24 |

Tested with Frappe 16.51.1, ERPNext 16.50.0 and Frappe HR 16.51.0.

## Installation

```bash
cd frappe-bench
bench get-app https://github.com/SDe-ER/card --branch main
bench --site your-site.local install-app card
bench --site your-site.local migrate
```

For Docker, add CARD to the `apps.json` of an official
[frappe_docker](https://github.com/frappe/frappe_docker) custom image.

**Upgrading:** take a full backup and run `bench migrate` on a restored copy of the site first. CARD ships
idempotent patches; a migrate that fails on the copy must never be run on the live site.

## Development

```bash
bench --site your-site.local set-config developer_mode 1
bench --site your-site.local set-config allow_tests true
bench --site your-site.local run-tests --app card
```

Code style is enforced with `pre-commit` (ruff, prettier, semgrep). See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security and permissions

- Roles: **Card Manager**, **Card User**, **Card Supervisor** and **Card Operator**, added on top of
  ERPNext's own roles.
- Every action is checked on the server; hidden fields or buttons are never treated as permissions.
- Users see only the companies, projects and records they are permitted to.
- Postings and approvals use the user's own ERPNext rights; CARD does not widen them.

Report vulnerabilities privately to **<info@sdce.sa>**; do not open public issues. See
[SECURITY.md](SECURITY.md).

## Languages

Arabic and Urdu (right-to-left), English, Bengali and Hindi. Arabic covers the whole app; Bengali, Hindi
and Urdu cover the operator-facing screens. The name "Card" is never translated.

## Versions and releases

CARD follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Every change goes through a pull
request with CI and review; every release has a full documentation page.

| Version | Date | Highlights |
|---|---|---|
| [v4.1.0](docs/releases/v4.1.0.md) | 2026-10-25 | First production go-live candidate: unique chassis/plate numbers, upgrade from v1.0.1 rehearsed, isolation and concurrency fixes |
| [v4.0.0](docs/releases/v4.0.0.md) | 2026-10-19 | Equipment materials: operator requests, supervisor review, approval into draft Material Requests, tool custody |
| [v3.0.0](docs/releases/v3.0.0.md) | 2026-10-19 | CARD launcher, multi-machine transport, cards follow transports, equipment from ERPNext Asset |
| [v1.2.2](docs/releases/v1.2.2.md) | 2026-10-18 | Company isolation, protected equipment fields, permanent posting log |
| [v1.2.1](docs/releases/v1.2.1.md) | 2026-10-16 | Report filters for operational roles, print amounts |
| [v1.2.0](docs/releases/v1.2.0.md) | 2026-10-16 | Rental directions and customers, settings and roles, diesel and transport, accounting dimension |
| [v1.0.1](docs/releases/v1.0.1.md) | 2026-10-13 | Frappe 16.50/16.51 compatibility fixes |
| [v1.0.0](docs/releases/v1.0.0.md) | 2026-10-13 | First release |

A published release is not a deployment: which version runs on a site is decided and verified per site.

## Documentation

| Document | Content |
|---|---|
| [Version history](docs/releases/VERSION-HISTORY.md) | Every release with its full feature inventory |
| [Version comparison](docs/releases/VERSION-COMPARISON.md) | Features by version |
| [Which version should I use?](docs/releases/WHICH-VERSION.md) | Upgrade guidance |
| [Release policy](docs/releases/RELEASE-POLICY.md) | How releases are made and documented |
| [CARD Mobile](docs/mobile/README.md) | Phone app architecture, access, languages and device checklist |
| [Document templates](docs/templates/README.md) | Print and document designs |
| [CHANGELOG.md](CHANGELOG.md) | Changes by version |

## Contributing

Open an issue first, work on a branch with tests, keep `pre-commit` green, and open a pull request with a
Conventional Commits title. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

MIT © 2026 Shams Dubai Contracting Est. (SDCE). See [LICENSE](LICENSE).

The CARD name and logo belong to SDCE. "Frappe", "ERPNext" and "Frappe HR" are trademarks of Frappe
Technologies Pvt. Ltd., used here only to describe compatibility, in line with the
[ERPNext trademark policy](https://github.com/frappe/erpnext/blob/develop/TRADEMARK_POLICY.md).
