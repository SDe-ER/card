# Contributing to CARD

Thanks for your interest in improving CARD. CARD is a standalone app built on the Frappe Framework and maintained by SDCE.

## Ground rules

- **No real data.** Never put real company, supplier, operator, project or financial data in code, tests, fixtures, screenshots or issues. Use invented/demo data only.
- **Server-side logic.** Business logic and validation live in the DocType controllers and the app's `api` module — not in client scripts.
- **Standard-first.** Prefer standard Frappe/ERPNext mechanisms; never edit Frappe/ERPNext core.

## Development setup

You need a working [bench](https://frappeframework.com/docs) with **Frappe ≥ 16.50** and **ERPNext v16**.

```bash
# in your bench
bench get-app /path/to/card        # or your fork's URL
bench --site <dev-site> install-app card
cd apps/card
pre-commit install
```

## Tests

```bash
bench --site <dev-site> run-tests --app card
```

Add or update tests for any behaviour change. The suite covers the controllers plus install / desktop-icon / sidebar-fold / idempotency behaviour.

## Linting

This repo uses `pre-commit` (ruff, ruff-format, prettier). Run it before pushing:

```bash
pre-commit run --all-files
```

## Pull requests

1. Branch off `main` (or the target branch) with a descriptive name.
2. Keep each PR focused; every changed line should trace to the stated task.
3. **PR titles follow [Conventional Commits](https://www.conventionalcommits.org/)** — e.g. `fix(install): …`, `feat(reports): …`, `docs: …`. CI enforces this.
4. Update `CHANGELOG.md` for user-facing changes.
5. Ensure CI is green (tests on Frappe version-16, linters, PR-title check).
6. A maintainer review is required (see `.github/CODEOWNERS`).

## Reporting bugs and requesting features

Use the issue templates. For **security vulnerabilities**, do not open a public issue — email **info@sdce.sa** (see [SECURITY.md](SECURITY.md)).

## Document design library

All newly created or revised printable designs belong under `card/templates/documents/`:
operation cards, invoices, receipts, account statements, diesel reports and other forms.
Follow `card/templates/AGENTS.md` and the template catalog before adding a design.
Commit editable sources, required assets, print-ready PDF, previews and validation notes together.
Company-specific branding explicitly supplied for a template stays within that template; do not
hardcode it into shared application behavior. Blank branded forms may be archived with the owner's
explicit permission; real transactions, personal data and financial records remain prohibited.

Archiving a design is not a deployment or installation of an ERPNext Print Format. Existing
runtime templates and fixtures remain at their canonical application paths.
