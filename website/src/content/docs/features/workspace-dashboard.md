---
title: Workspace & Dashboard
description: The Card workspace in the ERPNext Desk — number cards, charts, shortcuts, the launcher (Dock), sidebars and navigation.
sidebar:
  order: 1
---

## Overview

Card Desk opens on the **Card** workspace: a dashboard with key figures of the last month, two monthly charts and
shortcuts to the screens used every day. Around it, the Card launcher (Dock) gives ten entries, each opening a
sidebar with the DocTypes, pages and reports of one area. Users reach every Card screen from these two places
without searching.

All figures on the workspace are read with the user's own permissions: a user limited to some companies sees only
the figures of those companies, and amounts a user may not read are not shown.

<!-- screenshot: workspace-dashboard-overview -->
![Workspace number cards and charts](../../../assets/screenshots/en/workspace-dashboard-overview.webp)
*Workspace number cards and charts*

## Key concepts

| Concept | Meaning |
|---|---|
| **Workspace** | The **Card** Desk page at `/app/card`, shipped as a fixture. |
| **Number card** | A tile with one figure (count or sum) on the workspace. |
| **Dashboard chart** | A bar chart by month on the workspace. |
| **Launcher (Dock)** | The Card app rail with ten entries. Each entry opens a **sidebar**. |
| **Sidebar** | The navigation list of one area (for example Movement & Transport). |
| **Desk icon** | The **Card** icon on the Desk and on the apps screen, with the Card logo. |

## Features

### Opening Card

- **Desk icon** — the Card icon on the Desk opens the Card workspace. On the apps screen (`/apps`) the entry
  **Card** opens the Desk and **Card Mobile** opens the phone app at `/cdms`.
- The **Card** entry is shown to users who can read at least one Card Desk document (Card Equipment, Card Monthly
  Card, the supplier and customer registries, Equipment Transport, Project Diesel Fill, Equipment Needs Review or
  Employee Tool Custody). It is hidden from Website Users and from operators.
- The **Card Mobile** entry is shown to users who may open the phone app (see [Card Mobile](/card/features/card-mobile/)).

### Number cards

The workspace shows eleven number cards. Labels are stored in Arabic and shown translated in other languages.
The first column is the name the Card workspace shows in English.

| Number card | Arabic label | What it shows |
|---|---|---|
| Rented equipment (Card) | المعدات المؤجرة | Count of Card Equipment with ownership «إيجار» (Rented) |
| Draft cards (Card) | كروت مسودة | Count of monthly cards still in draft |
| Supplier operating value - last month | تكلفة إيجار من موردين - الشهر الماضي | Supplier net amount of last month's cards (rented-from-supplier and sub-rental) |
| Operating value for customers - last month | قيمة تشغيل لعملاء - الشهر الماضي | Customer net amount of last month's cards (rented-to-customer and sub-rental) |
| Internal operating value - last month | قيمة تشغيل داخلي - الشهر الماضي | Hours (or working days) × internal operating rate of owned and third-party equipment |
| Cards without internal rate (Card) | كروت بدون سعر داخلي | Last month's cards with no supplier or customer side and no internal rate |
| Operating hours without rate (Card) | ساعات تشغيل بدون سعر داخلي - الشهر الماضي | The operating hours of those cards |
| Cards last month | كروت الشهر الماضي | Count of submitted cards of last month |
| Total Diesel Litres | إجمالي لترات الديزل | Sum of litres of submitted diesel fills |
| Total Diesel Cost | إجمالي تكلفة الديزل | Sum of the amount of submitted diesel fills |
| Total Transport Cost | إجمالي تكلفة النقل | Sum of the amount of submitted transports |

:::note
Each value stays in its own figure: a card that has two sides (for example an owned machine rented to a customer
that also has an internal rate) counts in both, and the figures are never added into one number. The internal rate
is a restricted field of Card Equipment; a user who cannot read it gets no internal value and no missing-rate count.
:::

### Charts

| Chart | Arabic label | Content |
|---|---|---|
| Monthly Card Amounts | مبالغ الكروت الشهرية | Bars per month over the last year, in three separate series: supplier rental cost, customer operating value and internal operating value |
| Monthly Diesel Cost | تكلفة الديزل الشهرية | Sum of the amount of submitted diesel fills per month over the last year |

The Monthly Card Amounts chart uses its own chart source, **Card Monthly Values**. It is computed for each user
from the cards that user may read and is never served from a shared cache, so one company's totals never reach a
user of another company.

### Shortcuts

The workspace groups its shortcuts in four blocks:

- **Operation** — Monthly Cards, Assignments, Equipment, **New Card** (opens a new Card Monthly Card).
- **Parties** — Suppliers Summary, Supplier Statement, Equipment Customers, Customers Summary, Customer Statement.
- **Diesel and Operations** — Equipment Diesel Consumption, Transport Cost by Project, Operating Cost by Project.
- **Accounting** — Purchase Invoice, Sales Invoice, Payment Entry (the standard ERPNext lists).

<!-- screenshot: workspace-dashboard-shortcuts -->
![Shortcuts and report links](../../../assets/screenshots/en/workspace-dashboard-shortcuts.webp)
*Shortcuts and report links*

### Dashboard layout (v4.10.0 — not released yet)

The **Card** workspace opens with the operations dashboard, top to bottom:

1. **Header:** the title and three shortcuts: a new monthly card, a new equipment transport and the customer statement.
2. **Financial performance — last month:** customer operating value, supplier operating value (the supplier rental cost, the same figure as the monthly values chart) and internal operating value. Amounts are the full figures with thousands separators. A user without money read on monthly cards sees "N/A" in these cards and no amounts in the chart; no card is read for that user, and no error dialog is shown. The workspace is visible only to Card Manager, Card User and Accounts Manager, the roles that can read monthly cards. Card Operator and Card Supervisor cannot read monthly cards and do not see it.
3. **Operations last month:** cards last month, rented equipment and the number of loads.
4. **Needs review:** draft cards, cards without an internal rate and operating hours without a rate. The number shows the state; each card opens its filtered list.
5. **Monthly values chart** (full width), with five shortcuts underneath, each with its count.
6. **Links in three groups:** customers, suppliers, and diesel and operations.
7. **Latest monthly cards:** a Quick List of the most recent cards.

Every link on the dashboard is also in the **Card** sidebar. The supplier statement A4 opens the supplier statement report, from which it can be printed in A4.

### Launcher (Dock)

The Card launcher has ten entries, in this order. Each opens a sidebar.

| Entry | Arabic | Sidebar content |
|---|---|---|
| Dashboard | لوحة القيادة | The Card workspace, Card Monthly Card, Equipment Transport |
| Equipment | المعدات | Card Equipment, Card Equipment Type, Card Equipment Category |
| Movement & Transport | الحركة والنقل | Equipment Transport, Card Equipment Assignment, Transport Cost by Project |
| Operating Units | الوحدات التشغيلية | Operating units (Card Equipment), Card Equipment Assignment |
| Operation Cards | كروت التشغيل | Card Monthly Card, Operating Cost by Project |
| Expenses | المصروفات | Project Diesel Fill, Equipment Transport, Purchase Invoice, Asset Repair, diesel consumption and analysis reports, Equipment Expenses Without Equipment |
| Materials | المواد والمشتريات | Equipment Needs Request and Review, the Tool Custody page, Employee Tool Custody, Material Request, Stock Entry, the catalog (Item), equipment makes and models, parts fitment, and the materials reports |
| Suppliers & Customers | الموردون والعملاء | Card Equipment Supplier and Customer, supplier and customer statements and summaries |
| Reports | التقارير | Every Card report (statements, diesel, settlement, margin, unbilled work, integrity, maintenance, downtime, meters, asset mapping, transport, location history, operating cost) |
| Settings | الإعدادات | Card Settings |

Entries a user may not open are filtered out by Frappe when the launcher is built.

:::tip[Launcher on upgraded sites]
Frappe keeps a site's or a user's saved Dock layout as the whole rail. After every migrate Card adds to such a
layout any shipped entry it does not name yet, in the shipped order, without removing or reordering the user's own
rows. A layout saved after the shipped one is left untouched.
:::

### Desk pages

| Page | Route | Roles | Purpose |
|---|---|---|---|
| Card Monthly Posting | `/app/card-monthly-posting` | Card Manager, System Manager | Pick a company and a month and preview the monthly posting per party before building the draft invoices. See [Invoicing & posting](/card/features/invoicing-posting/) |
| Tool Custody | `/app/tool-custody` | Card Supervisor, Card Manager, Stock Manager, System Manager | Hand over, return and track tools in employee custody. See [Tool custody](/card/features/tool-custody/) |

### Connections on ERPNext forms

Card adds a **Card** group to the Connections tab of four standard forms, without removing the connections of
ERPNext or other apps:

| Form | Card connections |
|---|---|
| Supplier | Card Equipment, Card Monthly Card, Project Diesel Fill, Equipment Transport (as transporter) |
| Customer | Card Equipment Customer, Card Monthly Card |
| Project | Card Monthly Card, Card Equipment Assignment, Project Diesel Fill, Equipment Transport, Card Equipment (current project) |
| Asset | Card Equipment |

## Permissions

| What | Who sees it |
|---|---|
| Workspace and shortcuts | Users with access to the Card module; each shortcut opens only if the user may read its target |
| Number cards and charts | Computed with the user's DocType rights, Company User Permissions and field levels |
| Card Monthly Posting page | Card Manager, System Manager |
| Tool Custody page | Card Supervisor, Card Manager, Stock Manager, System Manager |

## Related

- [Introduction](/card/getting-started/introduction/)
- [Monthly cards](/card/features/monthly-cards/)
- [Reports overview](/card/reports/overview/)
- [Roles & permissions](/card/features/roles-permissions/)
