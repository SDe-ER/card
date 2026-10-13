<div align="center">

<img src="card/public/images/card-logo.svg" alt="CARD logo" height="96">

<h1>CARD</h1>

**Equipment rental and operation cards for ERPNext**

إدارة المعدات وكروت التشغيل الشهرية

[![CI](https://github.com/SDe-ER/card/actions/workflows/ci.yml/badge.svg)](https://github.com/SDe-ER/card/actions/workflows/ci.yml)
![Release](https://img.shields.io/badge/release-v1.0.1-1F876C)
![Frappe](https://img.shields.io/badge/frappe-v16-blue)
![License](https://img.shields.io/badge/license-MIT-green)

<br>

<img src=".github/images/card-landing.png" alt="CARD workspace" width="90%">

<br>

[Features](#key-features) · [Installation](#installation) · [Development](#development) · [Releases](#release-history) · [Contributing](#contributing)

</div>

---

## What is CARD

CARD is a standalone Frappe application for contractors that own and rent heavy equipment. It tracks every machine, assigns it to projects, records daily operating hours on a monthly card, and turns that card into a supplier-ready amount with additions and deductions.

CARD follows the same design principles as Frappe HR: one master record per asset (like **Employee**), one transaction per period (like **Salary Slip**), and everything linked to ERPNext's Company, Project and Supplier.

## Key Features

<details open>
<summary><b>Equipment master</b></summary>

- **Card Equipment** with type, category, ownership (owned or rented), owner/supplier and company.
- **Card Equipment Type** and **Card Equipment Category** for clean classification.
- Standard daily hours per equipment, used to prorate daily rates.

<img src=".github/images/card-equipment.png" alt="Card Equipment" width="85%">
</details>

<details open>
<summary><b>Project assignment</b></summary>

- **Card Equipment Assignment** links a machine to a project and site for a period.
- Prevents a machine from being double-counted across projects.
</details>

<details open>
<summary><b>Monthly operation card</b></summary>

- **Card Monthly Card** per equipment, shift and month, with a day-by-day grid (date, weekday, day status, operating hours, stoppage).
- Automatic totals: working days, total operating hours, amount, additions, deductions and **net amount**.
- Validations: one card per equipment, shift and month; every day must fall inside the card month.
- Owned equipment produces no supplier amount; rented equipment syncs to its supplier on submit.

<img src=".github/images/card-monthly-card.png" alt="Card Monthly Card" width="85%">
</details>

<details open>
<summary><b>Suppliers and reports</b></summary>

- **Card Equipment Supplier** with running balances.
- **Equipment Suppliers Summary** and **Equipment Supplier Statement** reports.
- Workspace with number cards (rented equipment, draft cards, last month amounts, last month cards) and a monthly amounts chart.

<img src=".github/images/supplier-statement.png" alt="Equipment Supplier Statement" width="85%">
</details>

### Billing rule (daily rate)

For equipment billed **per day**, CARD prorates by actual operating hours:

```
hourly_rate = daily_rate / standard_daily_hours
amount      = total_operating_hours × hourly_rate
net_amount  = amount + total_additions − total_deductions
```

Example: daily rate 600, standard day 10 hours, 88 operating hours → 88 × 60 = **5,280**.

## Under the Hood

CARD is built on the [Frappe Framework](https://frappeframework.com) and runs alongside these open-source applications:

| Dependency | Role | Tested with |
|---|---|---|
| [Frappe Framework](https://github.com/frappe/frappe) | Full-stack web framework | 16.51.1 |
| [ERPNext](https://github.com/frappe/erpnext) | Company, Project, Supplier, accounting | 16.50.0 |
| [Frappe HR](https://github.com/frappe/hrms) | Optional, for HR-linked workflows | 16.50.0 |

Runtime: Python 3.14, Node.js 24, MariaDB 10.6, Redis.

> CARD is an independent, open-source app. It is not affiliated with, endorsed by, or maintained by Frappe Technologies.

## Installation

### Bench

```bash
cd frappe-bench
bench get-app https://github.com/SDe-ER/card --branch main
bench --site your-site.local install-app card
bench --site your-site.local migrate
```

### Docker (frappe_docker)

Add CARD to your `apps.json` and build a custom image:

```json
[
  { "url": "https://github.com/frappe/erpnext", "branch": "version-16" },
  { "url": "https://github.com/SDe-ER/card", "branch": "main" }
]
```

```bash
docker build \
  --build-arg APPS_JSON_BASE64=$(base64 -w 0 apps.json) \
  --tag your-registry/erp:card-v1.0.1 \
  --file images/custom/Containerfile .
```

Then deploy the image and run:

```bash
bench --site your-site.local install-app card
bench --site your-site.local migrate
```

### Upgrading

Always take a full backup and run `bench migrate` on a restored copy of production first. CARD ships idempotent patches; a migrate that fails on the copy must never be run on production.

## Development

```bash
bench get-app https://github.com/SDe-ER/card --branch main
bench new-site card.localhost --install-app erpnext
bench --site card.localhost install-app card
bench --site card.localhost set-config developer_mode 1
bench start
```

Run the tests:

```bash
bench --site card.localhost set-config allow_tests true
bench --site card.localhost run-tests --app card
```

Code style is enforced with `pre-commit` (ruff, prettier, semgrep). Commits follow [Conventional Commits](https://www.conventionalcommits.org).

## Release History

| Version | Date | Highlights |
|---|---|---|
| **v1.0.1** | 2026-10-13 | Workspace moved to module `Card`; Frappe 16.50 sidebar migrated with all items; legacy `Card (Custom)` module retired; `net_amount` backfilled for cards submitted before v1.0. |
| **v1.0.0** | 2026-10-13 | First standalone release: equipment master, assignments, monthly cards, suppliers, reports and workspace. |

Full notes: [CHANGELOG.md](CHANGELOG.md) · [Releases](https://github.com/SDe-ER/card/releases)

## Contributing

1. Open an issue describing the bug or feature.
2. Create a branch, add tests, and keep `pre-commit` green.
3. Open a pull request with a Conventional Commits title.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Please report vulnerabilities privately to **info@sdce.sa**. Do not open public issues for security reports. See [SECURITY.md](SECURITY.md).

## License

MIT © 2026 Ahmed Shehab ([@SDe-ER](https://github.com/SDe-ER)). See [LICENSE](LICENSE).

## Logo and Trademark Policy

The CARD name and logo belong to the project's author. "Frappe", "ERPNext" and "Frappe HR" are trademarks of Frappe Technologies Pvt. Ltd. and are used here only to describe compatibility, in line with the [ERPNext trademark policy](https://github.com/frappe/erpnext/blob/develop/TRADEMARK_POLICY.md).

<br>

<div align="center">
<sub>Built by <a href="https://github.com/SDe-ER">Ahmed Shehab</a> · Screenshots use fictional demo data.</sub>
</div>
