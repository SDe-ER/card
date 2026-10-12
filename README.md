# Card

Monthly equipment operation cards for tracking rented and owned equipment, daily working hours, and monthly amounts — with an Arabic (RTL) interface.

## Features

- **Equipment registry** — DocTypes for equipment, categories, types, suppliers, and equipment assignments.
- **Monthly operation cards** — record hours worked per day; the monthly amount is calculated as total working hours × approved hourly rate.
- **Rate derivation** — hourly rate is derived from the daily rate divided by the daily hours.
- **Owned equipment** — equipment marked as owned ("ملك") has an amount of 0.
- **Adjustments** — child-table adjustments produce the net monthly amount.
- **Supplier registry** — suppliers are synced on submit and cancel; supplier totals flow into standard reports.
- **Script Reports** — "Equipment Suppliers Summary" and "Equipment Supplier Statement".
- **Workspace** — a "Card" workspace with number cards, a dashboard chart, and shortcuts, plus an app-owned desktop icon with logo.
- **Arabic (RTL) UI** — labels and layout designed for right-to-left use.

## Requirements

- Frappe / ERPNext **v16**
- Python **3.11+**
- A Frappe bench with a running site

## Installation

### Fresh site

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app card
bench migrate
```

### Site with a legacy custom Module Def "Card"

If the site already has a custom Module Def named "Card" (for example when migrating an existing setup), install with `--force`. The installer re-points the existing Module Def to this app and never deletes it:

```bash
bench install-app card --force
bench migrate
```

## Usage overview

- **Workspace "Card"** — entry point with number cards, a dashboard chart, and shortcuts to the module's records.
- **DocTypes** (module *Card*): Card Equipment, Card Equipment Assignment, Card Equipment Category, Card Equipment Type, Card Equipment Supplier, Card Monthly Card, plus the child tables Card Monthly Card Adjustment and Card Monthly Card Day.
- **Reports** — Equipment Suppliers Summary and Equipment Supplier Statement.
- **Business logic** — rate and amount calculations, plus supplier sync, are implemented in the DocType Python controllers and the app's API module.

## Running tests

```bash
bench --site <site> run-tests --app card
```

The suite includes controller tests and install/desk-icon/idempotency tests.

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/card
pre-commit install
```

Pre-commit runs ruff, eslint, prettier, and pyupgrade.

## License

MIT
