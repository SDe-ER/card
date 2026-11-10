---
title: Transport
description: Equipment Transport — move one or more machines between projects, workshops, storage and suppliers, with cost responsibility, cost center and assignment updates.
sidebar:
  order: 13
---

## Overview

An **Equipment Transport** records a move of one or more machines. It does two jobs at once:

1. **Location transfer** — when it is submitted, each machine's project assignment is closed and, for a move to a
   project, a new one is opened. This is how CARD knows where every machine is and which project its monthly cards
   belong to.
2. **Transport cost** — it records who pays the transporter and who finally bears the cost, the amount, its split
   over the machines and the cost center it is charged to, so the move can reach the transporter's monthly invoice and
   the cost reports.

The user picks the machines and the destination; where each machine comes from is read from its history and is never
typed.

<!-- screenshot: transport-form -->

## Key concepts

| Concept | Meaning |
|---|---|
| **Items** | The equipment table: one row per machine, with its **Cost share** and its derived **Current place** and **Movement**. |
| **Route** | **From** (derived from the first machine) and **Destination**: Project, Workshop, Storage or Supplier. |
| **Transport responsibility** | One scenario that sets who pays the transporter (**payer**) and who finally bears the cost (**cost bearer**). |
| **Cost project** | For a move the company bears, the project explicitly chosen to carry the cost — never assumed from the origin or destination. |
| **Financial decision** | For a move the company pays but recharges, the Accounts Manager's decision: bill the customer, absorb, recover from the equipment supplier, or return for correction. |
| **Move-day rule** | Which project gets the move day on a project-to-project move (recorded on the transport). |

Transports are numbered `TRN-00001`, … and are submittable, with a change history.

## Features

### Entry form

The form follows the order of the work:

1. **Equipment ownership** and, for a rented machine, the **Equipment supplier**. Both are taken from the first
   machine when left empty.
2. **Equipment** table — the machine picker is filtered by company, ownership and equipment supplier.
3. **Route** — From and the destination.
4. **Cost responsibility** — the scenario and what it needs.
5. **Cost and date** — Transporter cost, Agreed amount (not company cost), Transport supplier, Cost Center, **Date**
   (today by default), **Transport method** (Truck Head, Winch, Low-bed, Self-driven, Other), Company, Remarks.
6. **Intake source** (collapsed, optional).
7. **Financial decision** (shown only when one is needed).
8. **Linked Records** (collapsed; shown once something is linked or the transport is submitted): Created assignment,
   Previous assignment, Purchase Invoice, GL posting, Posted, Amended From, Cancel Reason.

With a single company, the company is filled in and hidden.

### Items

- One transport can carry several machines; a machine cannot be listed twice.
- Every machine must belong to the transport's company.
- As soon as a machine is picked, the form shows its **Current place** (Project, Workshop, Storage or Supplier, with
  the project or place). The server reads it again on save.
- **Movement** is derived per row: **First entry** (first move to a project, or from a supplier), **Transfer**, **To
  workshop**, **To storage** or **Return to supplier**.

### Route: From and To

| Destination | Required | Rules |
|---|---|---|
| **Project** | **To project** | A move to the project the machine is already on is refused. |
| **Workshop** / **Storage** | **To place** (an ERPNext Location) | A move to the place the machine is already at is refused. |
| **Supplier** | — | Only rented machines return to a supplier; an owned machine is refused. All machines must come from the same project, which is kept as the transport's project. |

**From** is never typed: it is read from the machine's open assignment, else its last submitted transport, else the
company's initial place (see [Assignments & Locations](/card/features/assignments-locations/#current-place-of-a-machine)).
The header shows the first machine's place; each row keeps its own.

The project of the transport (destination, or the project left on a return to the supplier) must belong to the
transport's company.

### Responsibility scenarios

**Transport responsibility** is mandatory. The scenario sets the payer and the cost bearer, which are stored apart:

| Scenario | Payer | Cost bearer | Needs | Financial status |
|---|---|---|---|---|
| Company bears the cost | Company | Company | Transport supplier, Transporter cost, Cost project (unless the destination is a workshop or storage) | No decision needed |
| Company pays, bills the customer | Company | Customer | Transport supplier, Transporter cost | Pending |
| Company pays, recovers from equipment supplier | Company | Equipment Supplier | Transport supplier, Transporter cost | Pending |
| Equipment supplier bears the cost | Equipment Supplier | Equipment Supplier | — (optional agreed amount) | No decision needed |
| Customer pays the transporter directly | Customer | Customer | — (optional agreed amount) | No decision needed |
| Other party bears the cost | Other Party | Other Party | Other party type and party (optional agreed amount) | No decision needed |
| No transport charge | No charge | — | — | No decision needed |
| Responsibility needs review | — | — | — | — (never costed or posted) |

Rules:

- A move the company pays needs a transport supplier and a transporter cost above zero.
- When the company does not pay, the transporter cost and the shares are set to zero. The **Agreed amount (not
  company cost)** may record what was agreed with the paying party; it is information only and never company cost or
  posted.
- **Other party bears the cost** names the party: a Supplier, a Customer (neither disabled), or an active Employee of
  the transport's company.
- An API client that sends a payer and cost-bearer pair gets the matching scenario; a pair that matches no scenario is
  refused.
- Transports recorded before responsibility scenarios existed keep their read-only **Transport cost borne by** value
  (Company, Equipment Supplier or Customer) and their earlier rule.

### Cost project

For **Company bears the cost** to or from a project, the **Cost project** must be chosen explicitly. On a draft the
form offers **Use as cost project → Destination project / Source project** as shortcuts. The cost project must belong
to the transport's company and have a usable cost center (enabled, not a group, of that company).

### Cost center

The read-only **Cost Center** is set on save:

| Case | Cost center |
|---|---|
| Company bears the cost, on a project | The cost project's cost center |
| Company bears the cost, to a workshop or storage | The cost center of that place for the company (Card Settings, **Cost center per workshop / storage place**); the move is refused until it is set |
| Company bears the cost, overhead (API only) | The overhead cost center sent, checked for the company |
| Any other scenario | None |

### Cost share per machine

The transporter cost is split equally over the machines. Any share can be edited; a typed share is kept and the other
shares are rebalanced from what is left. The shares must add up to the transporter cost and cannot be negative;
clearing a share returns it to the equal split. Rounding cents go to the last row.

### Transport price per project

Card Settings has a table **Transport price per project** (project, **Transport amount**). For a move the company pays
to a project that has a row:

- an empty transporter cost is filled with the configured amount;
- a different amount can be entered only by a user with the **Transport price editor role** (Card Settings; Card
  Manager by default).

Projects without a row keep free entry. A transport saved again unchanged on the same project is not re-checked.

### Financial decision

A submitted transport whose cost the company pays but recharges is **Pending**. An **Accounts Manager** records the
decision with **Record financial decision**:

| Cost bearer | Decisions |
|---|---|
| Customer | **Bill customer** — billing project of the company, active customer (the project's customer is suggested), agreed billing amount before VAT, authorization reference, billing on the monthly invoice or a separate invoice (a separate invoice needs the authorization document), and a confirmation tick. **Company absorbs** — a written reason. **Return for correction** — a note. |
| Equipment Supplier | **Recover from equipment supplier** — recovery amount and method (Deduct from monthly dues or Adjustment document). **Return for correction** — a note. |

- The status becomes **Approved**, or **Rejected** for a return for correction.
- Separation of duties: the person who created, edited or submitted the transport (or the transport it amends) cannot
  record its decision; no role is exempt.
- The decision fields are permission level 1 and can be changed only by this action, never by a save of the submitted
  transport. A timeline comment and a history entry record that a decision was made.
- The decision is a record. Whether it reaches invoices depends on the company's posting setting (below).

### Equipment status guard

A new transport of an equipment with status «منتهية» (Ended) is warned about or refused according to the company's
**Equipment status rule**. On save, a new transport or a changed destination checks every machine, otherwise only an
added machine; on submit every machine is checked again. Never stopped: a return to the supplier and a move of an
owned machine to a workshop or storage.

### Intake provenance

A transport entered from a paper sheet, a WhatsApp message or an email can keep where it came from (all optional):

- **Intake channel** — Manual, Paper, WhatsApp, Email or Other (set to Manual when another intake field is filled).
- **Intake source key** — an external reference. One live (draft or submitted) transport per company and key; a
  cancelled transport frees its key. Two companies may use the same key.
- **Intake received on** — cannot be in the future.
- **Intake evidence** — one private JPEG, PNG, WebP or PDF file; its **SHA-256** is computed by the server. The same
  evidence on another live transport of the company gives a warning only.

Intake never submits or posts anything.

:::note
Intake provenance was added after v4.7.0.
:::

### Assignment open and close

On **submit**, each machine is moved (see
[Assignments & Locations](/card/features/assignments-locations/#opening-and-closing-by-transport)): the previous
assignment is closed and, for a move to a project, a new one is opened according to the **Move-day rule** recorded on
the transport. Each row stores the assignments it closed and opened.

On **cancel** (a cancel reason is mandatory), CARD first checks that:

- no later transport of the same machine exists (also on the same day, after this one);
- no card day of the machine is recorded on the new project from the day its assignment started;
- the row's assignment links are exactly the ones this transport wrote, unchanged since;
- the transport's details are not changed in the cancel request.

Then it deletes the created assignment and reopens the previous one. A transport row cannot be inserted, changed or
deleted on its own; rows change only through their transport.

### Print

The **Equipment Transport Print** format shows the company name, the title (with Draft or Cancelled), document number,
date, project, transport supplier, From, To, transport method, remarks, the machines with their cost shares, the amount
summary and the amount in words, and three signature lines (Prepared By, Received By, Approved By). The page direction
follows the print language. See [Print Formats](/card/features/print-formats/).

<!-- screenshot: transport-print -->

### Posting

CARD never writes ledger entries; the monthly posting creates **draft** ERPNext invoices (see
[Invoicing & Posting](/card/features/invoicing-posting/)).

- Transports recorded before responsibility scenarios: a move the company paid becomes a line on the transport
  supplier's monthly draft Purchase Invoice, on its verified cost center.
- Transports with a responsibility scenario follow the company's **Transport responsibility posting** setting:

| Setting | Effect |
|---|---|
| Hold (default; also when empty) | Kept out of the monthly invoices; the **Transport Accounting Review** report lists them. |
| Post | Company-borne moves become the transporter's Purchase Invoice line on their cost allocation; an approved **Bill customer** decision on the monthly invoice adds the customer's Sales Invoice line from the agreed amount; an approved recovery is deducted on the same supplier's invoice (or left to an adjustment document). Moves the company does not pay, absorbed costs and undecided recharges are not posted. |

Switch to **Post** only after the accountant and the tax adviser agree. The cost reports count only what the company
finally bears on a cost project; agreed amounts of other payers are shown apart. See
[Reports: Transport Costs](/card/reports/transport-costs/).

## Workflow

1. Open **Equipment Transport** → **New**.
2. Pick the ownership (and equipment supplier), then add the machines.
3. Choose the destination: a project, a workshop or storage place, or the supplier.
4. Choose the **Transport responsibility**; fill the transport supplier, the transporter cost and the cost project
   when the company pays and bears it.
5. Check the date, the method and the cost shares; save.
6. Submit. The assignments open and close; the machines' current project follows.
7. For a recharged move, an Accounts Manager records the **financial decision**.
8. Print the transport for signature if needed.

## Permissions

| Role | Transport | Decision fields (level 1) |
|---|---|---|
| System Manager | Read, write, create, submit, cancel, delete | Read |
| Card Manager | Read, write, create, submit, cancel | Read |
| Card User | Read, write, create (draft only) | — |
| Accounts Manager | Read; records the financial decision | Read |

Users limited by Company User Permissions cannot create, read, change, submit or cancel another company's transport.

## Related

- [Assignments & Locations](/card/features/assignments-locations/)
- [Equipment](/card/features/equipment/)
- [Invoicing & Posting](/card/features/invoicing-posting/)
- [Suppliers & Customers](/card/features/suppliers-customers/)
- [Reports: Transport Costs](/card/reports/transport-costs/)
- [API: Transport](/card/api-reference/transport/)
