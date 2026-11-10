---
title: Roles & Permissions
description: The CARD roles, what each role can do, company isolation, field-level privacy of money values and separation of duties.
sidebar:
  order: 18
---

## Overview

CARD adds its own roles on top of the standard ERPNext roles and uses Frappe's permission system for everything:
DocType permissions, permission levels on fields, User Permissions and server-side permission hooks. The server
checks every action; CARD never treats a hidden field or a hidden button as a permission, and it never widens a
user's ERPNext rights. Postings and approvals run with the user's own rights.

<!-- screenshot: roles-permissions-role-list -->

## Key concepts

| Concept | Meaning |
|---|---|
| **CARD role** | A role created by CARD at install: Card Manager, Card User, Card Supervisor, Card Operator, Card Reviewer. |
| **ERPNext role** | Standard roles CARD also uses: System Manager, Accounts Manager, Accounts User, Stock Manager, Stock User, Purchase User. |
| **Permission level** | Fields at level 1 or 2 are readable or writable only by the roles granted that level. |
| **Company isolation** | A user limited to some companies by Company User Permissions never reads or writes another company's CARD records. |
| **Own records** | An *if owner* right: the user acts only on records he created. |

## Features

### The CARD roles

| Role | Desk | Purpose |
|---|---|---|
| **Card Manager** | Yes | Runs CARD: equipment, assignments, transports, monthly cards, diesel, settings (read), monthly posting, approvals of equipment needs |
| **Card User** | Yes | Daily data entry: equipment, monthly cards, transports and diesel fills (create and save, not submit); read-only catalog on CARD Mobile |
| **Card Supervisor** | Yes | Site supervisor: daily logs, meter readings, equipment needs reviews, parts fitment, tool custody |
| **Card Operator** | No | Operator: uses CARD Mobile only — his machines, his equipment needs requests and, where enabled, his own daily logs |
| **Card Reviewer** | Yes | Reviewer role for the approval workflow. Created on every site but granted to nobody, and not yet named in any DocType permission |

:::note
Card Operator is created without Desk access. An operator who also holds the ERPNext Employee role can still reach
the Desk through that role; give operators only the roles they need.
:::

### What each role can do

Main DocTypes, level 0 rights (from the role and action matrix shipped with the code):

| DocType | Read | Write / create | Submit / cancel |
|---|---|---|---|
| Card Equipment | System Manager, Card Manager, Card User, Accounts Manager, Card Supervisor | Write: System Manager, Card Manager, Card User. Create: System Manager, Card Manager | — |
| Card Equipment Assignment | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager | — |
| Card Monthly Card | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager, Card User | System Manager, Card Manager |
| Equipment Transport | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager, Card User | System Manager, Card Manager |
| Project Diesel Fill | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager, Card User | System Manager, Card Manager |
| Card Daily Log | System Manager, Card Manager, Card Supervisor, Card User, Card Operator (own) | System Manager, Card Manager, Card Supervisor, Card Operator (own) | Same as write |
| Equipment Meter Reading | Card Manager, Card Supervisor, Card User | Card Manager, Card Supervisor | Card Manager, Card Supervisor |
| Card Rate Agreement | System Manager, Card Manager, Accounts Manager, Card User | System Manager, Card Manager | System Manager, Card Manager |
| Card Stop Reason | System Manager, Card Manager, Card Supervisor, Card User, Accounts Manager | System Manager, Card Manager | — |
| Equipment Needs Request | System Manager, Card Manager, Card Supervisor, Card Operator, Card User | System Manager, Card Manager, Card Supervisor, Card Operator | Submit: same as write. Cancel: System Manager, Card Manager, Card Supervisor |
| Equipment Needs Review | System Manager, Card Manager, Card Supervisor, Card User | System Manager, Card Manager, Card Supervisor | System Manager, Card Manager, Card Supervisor |
| Employee Tool Custody | System Manager, Card Manager, Stock Manager, Card Supervisor, Card User | System Manager, Card Manager, Stock Manager, Card Supervisor | Submit: same as write. Cancel: System Manager, Card Manager, Stock Manager |
| Card Equipment Supplier / Customer | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager | — |
| Card Equipment Part (fitment) | System Manager, Card Manager, Card Supervisor | System Manager, Card Manager, Card Supervisor | — |
| GL Posting Log | System Manager, Accounts Manager, Card Manager | Nobody (written by CARD only) | — |
| Card Settings | System Manager, Accounts Manager, Card Manager | System Manager, Accounts Manager | — |

Deleting is limited to System Manager on most DocTypes (Card Manager also on equipment needs and tool custody).

### Actions limited to specific roles

| Action | Who may do it |
|---|---|
| Build and post the monthly draft invoices; open the CARD Monthly Posting page | Card Manager, System Manager |
| Approve an equipment needs review into draft Material Requests | Card Manager, System Manager (and Material Request create) — never the review's preparer |
| Record the financial decision on a recharged transport | Accounts Manager — never the transport's creator, editor or submitter |
| Accept a correction of an edited CARD draft invoice | Accounts Manager, System Manager, with a reason |
| Link a hand-booked supplier invoice or a supplier accrual Journal Entry to CARD sources | Accounts Manager, Accounts User, System Manager |
| Bypass the period lock | The **Period lock override role** of Card Settings; every override is logged |
| Change the diesel supplier / approve a diesel price exception / save a zero price / change transport prices | The roles named on the Advanced Permissions tab of Card Settings |
| Refresh the supplier and customer registries | System Manager |

### Company isolation

Every operational CARD record belongs to one company, and the server keeps companies apart:

- Records with a **Company** field follow the user's **Company User Permissions**, as everywhere in ERPNext.
- CARD adds server-side permission hooks where the company comes from another record: an assignment belongs to its
  equipment's company, a monthly card to its equipment's company, a transport to its project's company, an
  equipment needs review to its project's company, tool custody to its employees' company, a diesel fill to its
  company. They apply to lists, report views, link searches, counts, single reads, saves, submits and cancels, and
  to REST calls.
- A new record is checked against the company the server *will* set, so a user limited to company A cannot create a
  record for company B by leaving the company empty.
- Sharing a record with a user of another company (DocShare) is refused for the scoped DocTypes.
- Supplier and customer registries are global, but a user limited to some companies sees only the parties that have
  cards in those companies, and their figures only for those companies.
- In Card Settings, a company-restricted user sees only the company rows, adjustment types and diesel prices of his
  companies, also in the change history.
- Reports and dashboard figures read only the records of the user's permitted companies.

Cross-company tests in the code prove for every server method that a company-A user aimed at company B is refused
or receives no company-B value, and that nothing is written.

### Field privacy and money visibility

**Card Equipment** has three field levels:

| Level | Fields | Read | Write |
|---|---|---|---|
| 0 | Identity, type, status, documents, operator | All readers | Card Manager, Card User, System Manager |
| 1 | Commercial terms: ownership, rental direction, lessor, customer, rates and rate types, contract, rental dates, daily hours, fuel and operator charged to, Asset, make and model, unit and components | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager |
| 2 | Financial: equipment cost center, Asset cost center, Asset purchase value, internal hourly rate, internal operating rate and its basis | System Manager, Card Manager, Accounts Manager | System Manager, Card Manager |

- A change to a level 1 commercial field needs a new **Reason for commercial change**.
- Frappe applies these levels to the form, the REST API, list and report views and exports. CARD also masks the
  values of every field above level 0 in new change-history (Version) rows of Card Equipment, keeping who changed it
  and when.
- Values CARD copies from the Asset to the equipment form contain only the fields the user may read.
- Dashboard figures that use the internal rate are hidden from users who cannot read level 2.
- **Equipment Transport**: the cost decision, billing and recovery fields are level 1, readable by System Manager,
  Card Manager and Accounts Manager; nobody writes them on the form (they are set by the financial decision action).
- **Project Diesel Fill**: the review fields are level 1.

:::caution[Planned]
Amounts on monthly cards are not yet restricted by role: anyone who can read a card sees its amounts. Money
visibility on monthly cards by role, and a server-side "hide prices from a role" setting, are planned.
:::

### Separation of duties

Implemented today:

- **Equipment needs** — the supervisor who submitted a review, and anyone who edited its draft, cannot approve it.
- **Transport financial decision** — the Accounts Manager who records it cannot be the transport's creator, editor or
  submitter.
- **Cancel reason** — cancelling a monthly card, transport or diesel fill needs a reason, which is stored and
  commented on the document.
- **Period lock overrides** are logged and commented on the document.

:::caution[Planned]
On monthly cards, the rule "whoever created or entered a card never approves it" is planned. Today a card is
submitted by Card Manager or System Manager without a creator check.
:::

### CARD Mobile access

CARD Mobile opens for users with a portal role (Card Operator, Card Supervisor, Card Manager, System Manager) and an
Active Employee linked to the user; a Card User without a portal role opens only the catalog. See
[CARD Mobile](/card/features/card-mobile/).

## Workflow

1. Create the ERPNext users and, for operators, link each to an Active **Employee** (User ID).
2. Give each user the CARD role of his job, plus the ERPNext roles he needs (for example Accounts Manager for
   accountants, Stock Manager for stores).
3. Add **Company User Permissions** for users who work for some companies only.
4. In Card Settings, set the **Period lock override role** and the roles of the Advanced Permissions tab.

## Related

- [Configuration](/card/getting-started/configuration/)
- [CARD Mobile](/card/features/card-mobile/)
- [Invoicing & posting](/card/features/invoicing-posting/)
- [Equipment needs](/card/features/equipment-needs/)
