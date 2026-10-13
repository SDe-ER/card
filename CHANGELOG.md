# Changelog

All notable changes to the Card app are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project will adopt
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) from the next release.

## [Unreleased]
### Planned
- Align the packaged `__version__` to `1.1.0` (it is `0.0.1` under tag `v1.0.0` — see the note in `1.0.0`).

## [1.0.0] — 2026-10-13
First official release as a standalone Frappe v16 app, at **exact production parity** with the
pre‑existing production‑native CARD setup (equipment DocTypes + monthly‑card workflow + two script
reports + Card workspace), converted from client/server scripts into an app with controllers,
reports, fixtures, and an idempotent installer.

### Added
- 8 DocTypes under module *Card* (Card Equipment, Card Equipment Assignment, Card Equipment Category,
  Card Equipment Type, Card Equipment Supplier, Card Monthly Card, + child tables Card Monthly Card
  Adjustment and Card Monthly Card Day).
- Script reports *Equipment Suppliers Summary* and *Equipment Supplier Statement* with supplier GL
  reconciliation (accrual credits / payment debits, opening/closing, matching difference).
- *Card* workspace (number cards, dashboard chart, shortcuts) and a single app‑owned desktop icon
  with the Card logo; the Arabic monthly print format `كارت تشغيل شهري`.
- Idempotent installer: adopts a pre‑existing custom Module Def "Card" (never deletes it), flips the
  8 DocTypes to `custom=0 / module=Card`, creates the `default_print_format` Property Setter,
  disables (never deletes) the legacy server/client scripts, ensures exactly one desktop icon, and
  appends the Card launcher to each entitled user's desktop layout (append‑only).
- Report controllers derive the company prefix dynamically from the global default company (no
  hard‑coded company name).

### Compatibility
- Frappe/ERPNext **v16** (validated on 16.33.0 and 16.36.1); `required_apps = ["erpnext"]`; no
  dependency on any other custom app.

### Known limitations
- The packaged `__version__` is `0.0.1` (bench scaffold default) while this release is tagged
  `v1.0.0`; they differ intentionally for v1.0.0 and will be reconciled to `1.1.0` next release.

### Deployment notes
- Installs on a legacy site with `install-app card --force` (adopts the existing Module Def).
- When baked into a Docker image whose runtime `sites/assets` is a volume symlink, card's static
  files must be materialized into the image's bench‑root `assets/card` (see README → *Baked into a
  Docker image*).
