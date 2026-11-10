---
title: Installation
description: Requirements, installing CARD with bench, what the installer creates, upgrading, and building CARD Mobile.
sidebar:
  order: 2
---

## Overview

CARD is a standard Frappe app. It is installed with `bench get-app` and `bench install-app`, on a site that already
runs ERPNext. The installer is self-contained: it creates the CARD roles, the Desk launcher, the workspace, print
defaults and the other records the app needs, so no manual step is required on the site after installation, apart
from the configuration described in [Configuration](/card/getting-started/configuration/).

## Requirements

| Component | Version |
|---|---|
| Frappe Framework | v16, 16.51 or later |
| ERPNext | v16 (required app). For ERPNext 16.54.0 or later use CARD 4.3.0 or later |
| Frappe HR | v16, optional |
| Python | 3.14 |
| Node.js | 24 (used by `bench build` for CARD Mobile) |

CARD is tested with Frappe 16.51.1, ERPNext 16.50.0 and Frappe HR 16.51.0. Its only required app is `erpnext`
(`required_apps` in `hooks.py`).

## Features

### Install with bench

Run these commands from your bench directory. Replace `<your-site>` with your site name.

```bash
cd frappe-bench
bench get-app https://github.com/SDe-ER/card --branch main
bench --site <your-site> install-app card
bench --site <your-site> migrate
```

`bench get-app` also runs the app's JavaScript build, which builds CARD Mobile (see
[Build CARD Mobile](#build-card-mobile)).

For Docker deployments, add CARD to the `apps.json` of a custom image built with the official
[frappe_docker](https://github.com/frappe/frappe_docker) tooling.

### What the installer creates

Before the DocTypes are synced, the installer:

- creates the CARD roles: **Card Manager**, **Card User**, **Card Supervisor**, **Card Operator** and
  **Card Reviewer**. Card Operator is created without Desk access;
- adopts any earlier in-site CARD customisation (a custom "Card" module and DocTypes) so that the app's files sync
  onto the existing tables without data loss;
- makes sure there is exactly one **Card** Desk launcher icon, with the CARD logo.

After the DocTypes are synced, the installer:

- sets the default print formats: **Card Monthly Card Print** for Card Monthly Card, **Project Diesel Fill Print**
  and **Equipment Transport Print** (an existing non-empty default is kept);
- creates a **CARD** Letter Head built from the default company (name, tax ID, phone, logo) — only when the site has
  no Letter Head at all;
- disables (never deletes) older Server Scripts and Client Scripts from an earlier in-site customisation, so the app
  controllers are the only logic in force;
- adds the Card launcher to the desktop layout of users who may see it.

The app also ships these records as fixtures, imported on every migrate:

| Fixture | Content |
|---|---|
| Workspace | The **Card** workspace with its number cards, charts and shortcuts |
| Workspace Sidebar and Sidebar | The Card navigation sidebars |
| Number Card, Dashboard Chart | The dashboard widgets of the Card module |
| Print Format | The legacy Arabic monthly card print «كارت تشغيل شهري», kept as an alternative |
| Role | Card Manager and Card User |
| Property Setter | List-view columns of Card Monthly Card |

The Desk launcher (Dock) with its ten entries, the sidebars, the CARD print formats and the reports are standard
files of the app.

On every migrate CARD also installs its bundled Noto print fonts for the bench user (best effort; a failure never
stops the migrate) and restores any launcher entry missing from a saved Dock layout.

:::caution[Card Equipment accounting dimension]
Posting to ERPNext needs the **Card Equipment** accounting dimension. It is not created by install or migrate. An
administrator creates it once with:

```bash
bench --site <your-site> execute card.dimension.ensure_card_equipment_dimension
```

Until it exists, monthly posting refuses to run and says so.
:::

### Patches

CARD ships idempotent migration patches (`card/patches.txt`, all in the post-model-sync phase). On a fresh install
Frappe marks them all as completed; on an existing site `bench migrate` runs the ones not yet applied. They cover,
among others: the CARD roles, Card Settings defaults, print defaults, party registries, transport items, equipment
identity keys, the application name translation clean-up, seeded stop reasons and the seeded diesel price schedule.
Running `bench migrate` twice must finish the second time with no change.

### Upgrade

1. Take a full backup of the site (database and files).
2. Restore it to a copy of the site and run `bench migrate` there first.
3. Check that the migrate ends without an error and that the Error Log has no new CARD error.
4. Only then run `bench get-app`/`bench update` for CARD and `bench --site <your-site> migrate` on the live site.

:::danger
A migrate that fails on the copy must never run on the live site.
:::

### Build CARD Mobile

CARD Mobile is a Vue 3 and frappe-ui app in the `frontend/` folder of the repository. The app's root `package.json`
defines the build scripts, as Frappe HR does:

| Script | What it does |
|---|---|
| `postinstall` | Installs the `frontend/` dependencies |
| `build` | Builds `frontend/` into `card/public/frontend/` and the page template `card/www/cdms.html` |
| `dev` | Starts the Vite development server against the bench |

`bench build` (and therefore `bench get-app` and `bench update`) runs `build`. The build output is not stored in
the repository; it is produced on the bench. After the build, CARD Mobile is served by the site at `/cdms`.

```bash
bench build --app card
```

### Check the installation

- `bench version` lists `card` with the installed version.
- The **Card** icon appears on the Desk for users who may open CARD, and opens the Card workspace.
- **CARD Mobile** appears on the apps screen (`/apps`) for users with a CARD Mobile role and an active Employee.

## Related

- [Introduction](/card/getting-started/introduction/)
- [Configuration](/card/getting-started/configuration/)
- [CARD Mobile](/card/features/card-mobile/)
- [Roles & permissions](/card/features/roles-permissions/)
