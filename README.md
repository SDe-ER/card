<div align="center">
	<img src="card/public/images/card-logo.svg" alt="CARD logo" height="80" width="80"/>
	<h2>CARD</h2>
	<p><b>Monthly equipment operation cards for ERPNext</b><br/>
	Track rented and owned equipment, daily working hours and monthly amounts, with supplier reconciliation against the General Ledger and an Arabic (RTL) interface.</p>

[![CI](https://github.com/SDe-ER/card/actions/workflows/ci.yml/badge.svg)](https://github.com/SDe-ER/card/actions/workflows/ci.yml)
[![Release](https://img.shields.io/badge/release-v1.0.1-06B58B)](https://github.com/SDe-ER/card/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](license.txt)
[![Frappe](https://img.shields.io/badge/frappe-%E2%89%A5%2016.50-1F876C)](https://frappeframework.com)

</div>

<!-- Hero and feature screenshots (captured on a throwaway demo site, fake data only) are added
     under .github/images/ in a follow-up commit; see the "Screenshots" section. -->

## What is CARD

CARD is a standalone [Frappe](https://frappeframework.com) v16 app that manages **monthly equipment operation cards** and **supplier reconciliation** for contracting and equipment-rental operations. It is **built on the Frappe Framework** and requires **ERPNext** for the shared company, supplier and accounting backbone.

It packages a set of equipment DocTypes, the monthly-card workflow, two script reports, and a *Card* workspace with an app-owned desktop icon — all installable on any Frappe v16 site with a single `install-app`.

## Key features

- **Equipment registry** — DocTypes for equipment, categories, types, suppliers and equipment assignments.
- **Monthly operation cards** — record hours worked per day; the monthly amount = total working hours × approved hourly rate.
- **Rate derivation** — the hourly rate is derived from the daily rate ÷ the daily hours; owned equipment (`ملك`) carries an amount of 0 (hours only).
- **Adjustments** — a child table of additions/deductions produces the net monthly amount.
- **Supplier reconciliation** — *Equipment Suppliers Summary* and *Equipment Supplier Statement* reports reconcile card totals against supplier GL entries (accrual credits / payment debits, opening/closing, matching difference).
- **Desk workspace** — a *Card* workspace (number cards, dashboard chart, shortcuts) and a single app-owned desktop icon with the CARD logo.
- **Arabic (RTL) UI** — labels and layout designed for right-to-left use; the monthly print format is `كارت تشغيل شهري`.

## Screenshots

> UI screenshots are captured on a throwaway demo site seeded with **fake data only** and stored under `.github/images/`. They are added in a follow-up commit on this branch — **no real company, supplier, operator, project or financial data is ever committed.**

## Under the hood

- [**Frappe Framework**](https://frappeframework.com) — the full-stack Python/JavaScript web framework CARD is built on (database layer, auth, REST API, Desk UI). *Dependency.*
- [**ERPNext**](https://github.com/frappe/erpnext) — provides Company, Cost Center, Project, Supplier, Asset and the General Ledger that CARD reconciles against. *Required app.*
- [**Frappe HR (HRMS)**](https://github.com/frappe/hrms) — Employee links used by equipment assignments. *Optional at runtime.*

CARD links only to standard Frappe/ERPNext/HR doctypes and its own doctypes — it has **no dependency on any other custom app**.

## Compatibility

| | Version |
|---|---|
| Frappe | **≥ 16.50** (validated on 16.51.1; v1.0.1+ required for ≥ 16.51) |
| ERPNext | **v16** (required app) |
| Frappe HR | **v16** (optional) |
| Python | **3.14** |

## Installation

### Fresh site (bench)

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench --site <site> install-app card
bench --site <site> migrate
```

### Site that already has a legacy custom Module Def "Card"

If the site already carries a custom Module Def named `Card` (e.g. a setup built with client/server scripts before this app existed), install with `--force`. The installer **adopts** the existing Module Def (re-points it to this app, `custom=0`) and never deletes it — deleting it would cascade-delete the data. It also, idempotently: flips the 8 Card DocTypes to `custom=0 / module=Card`, creates the `default_print_format` Property Setter, disables (never deletes) the legacy server/client scripts, ensures exactly one app-owned desktop icon, folds the frappe-16.50 navigation sidebar into the canonical `Card` one, and appends the Card launcher to each entitled user's desktop layout (append-only).

```bash
bench --site <site> install-app card --force
bench --site <site> migrate
```

### Baked into a Docker image (production)

Where Frappe apps are baked into the image rather than fetched on the host, add CARD from a verified source archive of the tag and install it inside the running backend container:

```dockerfile
# add on top of your existing Frappe/ERPNext v16 image
COPY --chown=frappe:frappe card-src /home/frappe/frappe-bench/apps/card
RUN env/bin/pip install --no-cache-dir -e apps/card \
 && bench build --app card \
 && mkdir -p assets/card && cp -aL apps/card/card/public/. assets/card/ \
 && rm -rf sites/assets
```

> **Asset note:** if your runtime mounts `sites/` as a volume whose `sites/assets` is a symlink to the image's `assets/` directory, CARD's static files must live in the image's bench-root `assets/card` (as above) — otherwise the volume masks them and `/assets/card/...` 404s.

Then, inside the backend container, ensure `card` is listed in `sites/apps.txt` and run `install-app card [--force]` + `migrate`.

## Development setup

```bash
# inside an existing bench with frappe >=16.50 and erpnext v16
bench get-app /path/to/card
bench --site <dev-site> install-app card
cd apps/card && pre-commit install
```

Run the tests:

```bash
bench --site <site> run-tests --app card
```

The suite covers the controllers plus install / desktop-icon / sidebar-fold / idempotency behaviour.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and our [Code of Conduct](CODE_OF_CONDUCT.md). This app uses `pre-commit` (ruff, ruff-format, prettier) and conventional PR titles.

## Security

Please report security issues privately to **info@sdce.sa** — see [SECURITY.md](SECURITY.md). Do not open public issues for vulnerabilities.

## Release history

See [CHANGELOG.md](CHANGELOG.md) and the [Releases](https://github.com/SDe-ER/card/releases) page.

## License

[MIT](license.txt) © 2026 Shams Dubai Contracting Est. (SDCE). Contact: info@sdce.sa

## Logo and Trademark Policy

The **CARD** name and the CARD logo are © Shams Dubai Contracting Est. (SDCE).

CARD is an independent application developed by SDCE and is **built on the Frappe Framework**. CARD is **not** a product of, and is **not** endorsed, sponsored or maintained by Frappe Technologies Pvt. Ltd. "Frappe", "Frappe Framework", "ERPNext" and "Frappe HR" are trademarks of Frappe Technologies Pvt. Ltd., referenced here only to identify the framework and the applications CARD depends on. Use of those names does not imply any affiliation or endorsement, and this project follows the [ERPNext Logo and Trademark Policy](https://github.com/frappe/erpnext/blob/develop/TRADEMARK_POLICY.md). No Frappe or ERPNext logos or wordmarks are used as CARD's own branding.

<div align="center">
	<img src="card/public/images/card-logo.svg" alt="CARD" height="40" width="40"/>
</div>
