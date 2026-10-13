# Card

**Monthly equipment operation cards** for Frappe / ERPNext v16 — track rented and owned equipment, daily working hours, and monthly amounts, with supplier reconciliation against the General Ledger and an Arabic (RTL) interface.

Card packages, as an official standalone Frappe app, a set of equipment DocTypes, the monthly‑card workflow, two script reports, and a Card workspace with an app‑owned desktop icon.

---

## Features

- **Equipment registry** — DocTypes for equipment, categories, types, suppliers, and equipment assignments.
- **Monthly operation cards** — record hours worked per day; the monthly amount = total working hours × approved hourly rate.
- **Rate derivation** — the hourly rate is derived from the daily rate ÷ the daily hours.
- **Owned equipment** — equipment marked owned (`ملك`) carries an amount of 0 (hours only).
- **Adjustments** — a child table of additions/deductions produces the net monthly amount.
- **Supplier registry** — suppliers are synced on submit/cancel; supplier totals feed the reports.
- **Script reports** — *Equipment Suppliers Summary* and *Equipment Supplier Statement*, both reconciling card totals against supplier GL entries (accrual credits / payment debits).
- **Workspace** — a *Card* workspace with number cards, a dashboard chart, shortcuts, and a single app‑owned desktop icon with the Card logo.
- **Arabic (RTL) UI** — labels and layout designed for right‑to‑left use; the monthly print format is `كارت تشغيل شهري`.

## Compatibility

| | Version |
|---|---|
| Frappe | **v16** (tested on 16.33.0, 16.36.1, and 16.51.1 — v1.0.1+ required for ≥16.51) |
| ERPNext | **v16** (required app) |
| HRMS | **v16** (Employee link; optional at runtime) |
| Python | 3.11+ |

`required_apps = ["erpnext"]`. Card links to standard ERPNext/HR doctypes (Company, Cost Center, Project, Supplier, Asset, Employee) and its own doctypes only — it has **no dependency on any other custom app**.

## Installation

### Fresh site (bench)

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench --site <site> install-app card
bench --site <site> migrate
```

### Site that already has a legacy custom Module Def "Card"

If the site already carries a custom Module Def named `Card` (e.g. migrating a setup that was built with client/server scripts before this app existed), install with `--force`. The installer **adopts** the existing Module Def (re‑points it to this app, `custom=0`) and never deletes it — deleting it would cascade‑delete the data. The app also, idempotently: flips the 8 Card DocTypes to `custom=0 / module=Card`, creates the `default_print_format` Property Setter, disables (never deletes) the legacy server/client scripts, ensures exactly one app‑owned desktop icon, and appends the Card launcher to each entitled user's desktop layout (append‑only).

```bash
bench --site <site> install-app card --force
bench --site <site> migrate
```

### Baked into a Docker image (production)

Where Frappe apps are baked into the image rather than fetched on the host, add Card to the image from a verified source archive of the tag and install it inside the running backend container:

```dockerfile
# add on top of your existing Frappe/ERPNext v16 image
COPY --chown=frappe:frappe card-src /home/frappe/frappe-bench/apps/card
RUN env/bin/pip install --no-cache-dir -e apps/card \
 && bench build --app card \
 && mkdir -p assets/card && cp -aL apps/card/card/public/. assets/card/ \
 && rm -rf sites/assets
```

> **Asset note:** if your runtime mounts `sites/` as a volume whose `sites/assets` is a symlink to the image's `assets/` directory, card's static files must live in the image's bench‑root `assets/card` (as above) — otherwise the volume masks them and `/assets/card/...` 404s.

Then, inside the backend container, ensure `card` is listed in `sites/apps.txt`, and run `install-app card [--force]` + `migrate`.

## Usage overview

- **Workspace "Card"** — entry point with number cards, a dashboard chart, and shortcuts.
- **DocTypes** (module *Card*): Card Equipment, Card Equipment Assignment, Card Equipment Category, Card Equipment Type, Card Equipment Supplier, Card Monthly Card, plus the child tables Card Monthly Card Adjustment and Card Monthly Card Day.
- **Reports**: Equipment Suppliers Summary, Equipment Supplier Statement.
- **Business logic** — rate/amount calculations and supplier sync live in the DocType Python controllers and the app's `api` module; the reports' logic lives in their `.py` files.

## Screenshots

Place screenshots under `docs/images/` and reference them here. Use a demo/sample company only — **do not include real company, supplier, operator, or financial data in committed screenshots.**

| | |
|---|---|
| Card workspace | `docs/images/workspace.png` |
| Monthly operation card | `docs/images/monthly-card.png` |
| Equipment Supplier Statement | `docs/images/supplier-statement.png` |

### Generating screenshots (demo data only)

Capture screenshots from a **throwaway demo site with invented data** — never from a production or customer site:

```bash
bench new-site demo.localhost --install-app erpnext --install-app card
bench --site demo.localhost execute card.demo.seed   # optional: add a seed module with fake data
bench --site demo.localhost browse --user Administrator
```

Seed a fake Company, a couple of suppliers (e.g. "Demo Equipment Co."), 2–3 equipment records, and one monthly card, then screenshot the workspace, a monthly card, and a supplier statement. Scrub anything identifying before committing. **Do not commit screenshots containing real company, supplier, operator, project, card, or financial data.**

## Running tests

```bash
bench --site <site> run-tests --app card
```

The suite covers the controllers plus install / desktop‑icon / idempotency behaviour (append‑only layout, adopt‑idempotent, reconcile‑idempotent, backing‑file guard).

## Contributing

This app uses `pre-commit` (ruff, eslint, prettier, pyupgrade):

```bash
cd apps/card
pre-commit install
```

## License

MIT — see `license.txt`. Author: Ahmed Shehab &lt;info@sdce.sa&gt;.
