---
title: Equipment Needs
description: Operator requests for parts and tools, the supervisor's review, management approval into draft ERPNext Material Requests, the /equipment-needs page, repeat requests and stock hints.
sidebar:
  order: 15
---

## Overview

Equipment Needs is how a machine's parts, consumables and tools are asked for, checked and turned into standard ERPNext
documents:

1. The **operator** of a machine asks for what it needs (**Equipment Needs Request**).
2. The **supervisor** of the project collects the requests, checks what is already on site and decides the quantities
   (**Equipment Needs Review**).
3. A **manager** who did not prepare the review approves it. Approval creates **draft Material Requests** in ERPNext,
   and draft tool handovers for tools; buying and stock then work in ERPNext as usual.

Parts and consumables belong to the machine; tools are the operator's custody (see
[Tool Custody](/card/features/tool-custody/)). CARD never posts to the ledger and never creates salary deductions or
penalties: a repeated request is only flagged for review.

<!-- screenshot: equipment-needs-review -->

## Key concepts

| Concept | Meaning |
|---|---|
| Request | One operator, one machine, one date; lines of parts or tools. Named `ENR-#####`. |
| Review | One project (optionally a date range); the lines of several requests. Named `ENV-#####`. |
| Request status | «قيد الانتظار» Pending → «قيد المراجعة» In review → «معتمد» Approved or «مرفوض» Rejected; moved by the review and the approval only. |
| Management approval | «قيد الانتظار» Pending or «معتمد» Approved, written by the server. |
| Supply route | «من المخزن» From store or «شراء للمشروع» Buy for project. |
| Repeat flag | **Asked recently**: the same item was asked for, or issued to, the same machine within the repeat window. |
| Fit for machine | The parts-fitment state of the item for the machine when it was asked for. |

## Features

### Equipment Needs Request

Fields:

- **Equipment** – required; **Equipment name** and **Project** are filled by the server. The project is the one the
  machine is on now (its open assignment); a machine that is not on a project cannot get a request.
- **Operator** (an Employee) – required; **Operator name**.
- **Date** – default today.
- **Entered by** and **Entered on behalf** – set by the server.
- **Review status** – read only.
- **Items** – at least one line; **Notes**.

Each line (**Equipment Needs Request Item**):

| Field | Rule |
|---|---|
| Kind | «قطعة غيار» Part (default) or «أداة» Tool |
| Needed item | An ERPNext Item, or leave it empty and write a **Description** |
| Quantity | Required, more than zero; **UOM** optional |
| Reason | Free text |
| Fit for machine | Set by the server from parts fitment (read only) |
| Reason for an item without a confirmed fit | Required on submit when the item has no confirmed fit for the machine |
| Asked recently / Last asked on | Set by the server (see *Repeat requests*) |

Who may ask:

- An operator asks only for a machine **he operates**: he is the equipment's operator, or he is on the machine's
  monthly card for the month.
- A Card Supervisor or Card Manager may enter a request **on behalf** of the operator; both names are kept.
- Operators see only their own requests.
- A request that is in a supervisor review cannot be cancelled; cancel the review first.

### The /equipment-needs page

`/equipment-needs` (**My equipment needs** / احتياجات معداتي) is a simple mobile web page where an operator asks for his
machine's needs with his own account, without Desk:

- a visitor who is not logged in is sent to the login page and back;
- it lists the machines assigned to the operator this month, with their project;
- each line is a **Part or consumable** or a **Tool**, with an item search (code, name, barcode or OEM number, 20
  results at most, following the catalog rules) or a free description, a quantity, a reason and, when needed, the
  reason for an item without a confirmed fit;
- **Send to supervisor** creates and submits the request at once;
- **My recent requests** shows the operator's last 20 requests with their status.

The page requires the user to be linked to an active Employee and to hold Card Operator, Card Supervisor, Card Manager
or System Manager. CARD Mobile (`/cdms`) offers the same request flow in its **New request** screen (see
[CARD Mobile](/card/features/card-mobile/)).

<!-- screenshot: equipment-needs-portal -->

### Equipment Needs Review

Fields: **Project** (required), **From date**, **To date**, **Supervisor**, **Review submitted by**, **Management
approval**, **Approved by**, **Approved on**, **Items**, **Notes**. The company comes from the project.

**Get requests** (on a saved draft) adds every line of the project's submitted, pending requests in the date range that
no other review holds. Lines can be added only this way; none can be typed. The requested quantity is copied and never
edited.

Each line (**Equipment Needs Review Item**):

| Field | Meaning |
|---|---|
| Request, Equipment, Operator, Kind, Description | Copied from the request (read only) |
| Needed item | The Item; may be matched here if the operator only described it |
| Requested qty | As the operator asked (read only) |
| Found on site | What is already available on site |
| Approved qty | What to supply (defaults to the requested qty); 0 refuses the line |
| Site inspection | «لم تتم المعاينة» Not inspected or «تمت المعاينة» Inspected, with an **Inspection note**; inspector and date set by the server |
| Supply route | From store (default) or Buy for project |
| Warehouse | Default: the company's main store |
| In stock | Live stock hint (see below); never stored |
| Asked recently, Fit for machine, Reason for an item without a confirmed fit | Copied from the request |
| Material Request, Tool custody, Handed over qty | Written by the server after approval |

A tool line with an approved quantity must be a stock item and not a fixed asset (a fixed asset's custodian is recorded
on the Asset). Submitting the review sets its requests to *In review*; cancelling it sets them back to *Pending*. An
approved review cannot be cancelled.

### Approval into draft Material Requests

**Approve** appears on a submitted review whose management approval is *Pending*, for **Card Manager** or **System
Manager**. The approver also needs the ERPNext right to create Material Requests (for example Stock User), and, for
tools, to create Employee Tool Custody records. Before anything is created:

- every approved line must have an Item and a warehouse;
- tools need the company's **Tool custody store** and a worker named on the request;
- a second click waits and then sees "already approved".

Approval creates, with the approver's own rights:

| Approved line | Created |
|---|---|
| Part, From store | Draft Material Request, type **Material Issue** |
| Part, Buy for project | Draft Material Request, type **Purchase** |
| Tool, From store | Draft custody **Handover** for the operator; the store confirms it later |
| Tool, Buy for project | Draft Material Request, type **Purchase**, and a draft custody **Handover** for the operator |

Each Material Request row carries the item, quantity, project, the project's cost center (else the company's default
cost center), the warehouse and, for parts, the **Card Equipment** dimension. Approval moves no stock. Each request then
becomes *Approved* when at least one of its lines was approved, otherwise *Rejected*.

### Reviewer is not the approver

The review records, on the server, its **Supervisor** (the reviewer), **Review submitted by** and every user who saved the
draft. None of them may approve it, whatever their role (Administrator and System Manager included). The **Approve**
button is hidden from them and the server refuses the approval.

### Repeat requests

When a request line names an Item, CARD checks whether the same item was asked for the same machine (another submitted
request) or issued to it (a submitted Material Issue Stock Entry carrying the machine) within the repeat window. If so,
the line gets **Asked recently** and **Last asked on**.

The window is **Flag a repeated request within (days)** of the company (Card Company Settings), else the value in Card
Settings (tab *Materials*, default 30). The flag is a hint for the supervisor only. The **Repeat Equipment Requests**
report (filters *Project*, *Equipment*) lists the flagged lines.

### Stock hints

The **In stock** figure of a review line is read live with the reader's own ERPNext rights:

- only for a user whose roles read Bin and Warehouse (not through a share or an owner-only right);
- only in the warehouses he may read, of the review's company;
- otherwise nothing is shown (never a false zero).

The figure is never stored on the review. The **Equipment Needs Summary** report (filters *Project*, *Management
approval*) groups the review lines by item with requested, found, approved and in-stock quantities, and removes the
stock column for any other reader.

### Purchase Order, Receipt and Invoice buttons

:::caution[Planned]
Buttons to create a Purchase Order, Purchase Receipt or Purchase Invoice from a CARD Material Request are not built.
CARD creates draft Material Requests only; the buying and stock team continues in ERPNext with its standard actions.
:::

### Settings

- Card Settings, tab **Materials**: **Main store**, **Tool custody store**, **Flag a repeated request within (days)**.
- Card Company Settings, section **Materials**: the same three values per company; empty means the Card Settings value.
  A company warehouse must be an enabled, non-group warehouse of that company.

## Workflow

1. The operator opens `/equipment-needs` (or CARD Mobile), picks his machine, adds lines and presses **Send to
   supervisor**.
2. The supervisor creates an **Equipment Needs Review** for the project, saves it and presses **Get requests**.
3. He records what was found on site, inspects, sets the approved quantities, supply routes and warehouses, and submits.
4. A Card Manager who did not prepare the review presses **Approve**.
5. The buying and stock team completes the draft Material Requests in ERPNext; the store confirms tool handovers.
6. Parts issued with a Stock Entry carry the machine, so their cost reaches it.

## Permissions

| Action | Roles |
|---|---|
| Create and submit a request for one's own machine | Card Operator |
| Create, submit, cancel, amend requests (also on behalf) | Card Supervisor, Card Manager, System Manager |
| Read requests | Card User (Card Operators read only their own) |
| Create, submit, cancel, amend reviews | Card Supervisor, Card Manager, System Manager |
| Approve a review | Card Manager, System Manager (not the reviewer, submitter or an editor; plus Material Request create right) |
| Read reviews | Card User |
| Equipment Needs Summary, Repeat Equipment Requests | System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager |

A user limited to some companies cannot create, read or change requests or reviews of another company.

## Related

- [Maintenance & Parts](/card/features/maintenance-parts/)
- [Tool Custody](/card/features/tool-custody/)
- [CARD Mobile](/card/features/card-mobile/)
- [Roles & Permissions](/card/features/roles-permissions/)
- [Materials & needs API](/card/api-reference/materials-needs/)
