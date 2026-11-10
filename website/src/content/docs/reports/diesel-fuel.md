---
title: Diesel and Fuel Reports
description: Expected against allocated diesel, allocated diesel per equipment, and reconciliation of diesel sessions with supplier invoices.
sidebar:
  order: 4
---

## Overview

CARD records diesel as **Project Diesel Fill** sessions: a direct fill to one machine, or a fill of a project tank
shared by the machines working on the project. The diesel reports turn those sessions into litres and cost per
machine, compare them with what the machine should have used, and check them against the suppliers' own invoices.
They are display-only: they never post to the ledger and never change a card's net amount.

## Key concepts

| Concept | Meaning |
|---|---|
| Recorded litres | Litres of direct fills to the machine. |
| Estimated litres | The machine's share of project-tank fills, split by its card hours for the month (not measured). |
| Allocated litres | Recorded plus estimated litres. |
| Unallocated | Tank fills of a project-month in which no card has hours: they cannot be split and stay unallocated. |
| Expected litres | Operating hours × (daily diesel consumption ÷ daily standard hours) of the equipment; or hours × the older per-hour expected consumption. |
| Delivery stream | The diesel suppliers whose sessions and invoices are matched together (one delegate, combined invoices). |

## Equipment Diesel Analysis

**Purpose.** Per equipment, project and month: expected litres from the card hours against the litres allocated from
submitted fills, with the variance. The variance compares expected and allocated litres, not measured consumption.

<!-- screenshot: diesel-analysis -->

**Filters**

- **Company** – required.
- **From month**, **From year** – required; default to the current month.
- **To month**, **To year** – optional; default to the start month.
- **Project**, **Equipment** – optional.

**Columns:** Equipment name, Equipment number, Project, Operating month, Operating hours, Daily diesel consumption
(litres per standard day), Expected litres, Allocated litres, Recorded litres (direct fills), Estimated litres (hours
split), Litres variance (expected vs allocated), Variance %.

**Totals.** Tiles **Operating hours**, **Expected litres**, **Allocated litres**, **Recorded litres**, **Estimated
litres** (orange when not zero) and **Litres variance** (green within the Card Settings reconciliation tolerance).

**Access.** System Manager, Card Manager, Card User, Accounts Manager.

**Notes.** Only submitted cards count. Equipment without any consumption figure has an empty expected value (never an
error).

## Equipment Diesel Consumption

**Purpose.** Per project and month in which submitted fills exist, the litres and cost allocated to each machine:
direct fills in full, tank fills pro rata by hours, and an **Unallocated** row for what cannot be split.

**Filters:** **Company** (required), **From date**, **To date**, **Project**, **Equipment**.

**Columns:** Equipment (or "Unallocated"), Project, Month, Allocated litres, Recorded litres (direct fills), Estimated
litres (hours split), Diesel cost.

**Totals.** None.

**Access.** System Manager, Card Manager, Card User, Accounts Manager.

:::note
Allocation is always made for a whole calendar month. The date filters only choose which project-months appear.
:::

## Diesel Invoice Reconciliation

**Purpose.** Compares CARD diesel sessions with the suppliers' own **Purchase Invoices** entered in the Desk. The litres,
the delivery charge and the fuel kind are read from the invoice line text (item name and description); the VAT basis
of each invoice is derived from its own figures. A difference is a point to review, never a confirmed over-billing,
missing invoice or missing payment. Nothing is created, changed or linked.

<!-- screenshot: diesel-invoice-reconciliation -->

**Filters**

- **Company** – required.
- **Diesel suppliers (one delivery stream)** – a multi-select of suppliers of the company's diesel sessions
  (`card.diesel_reconciliation.diesel_supplier_options`). The selected suppliers are matched as one stream; when
  empty, each supplier is its own stream.
- **From date** / **To date** – required; default to the start of the year and today.
- **Diesel sessions to include** – "Submitted and draft" (default) or "Submitted only".
- **Invoice date window (days)** – default 3.
- **Delivery charge up to (litres)** – default 60.

**Matching order**

1. **Linked** – a session that names the invoice.
2. **Per delivery** – an invoice of the stream dated from one day before to the window after the session whose
   diesel litres equal the session's, or equal it plus a delivery charge folded into the diesel line, or — when the
   invoice states no litres — whose gross or net divided by the session price gives the session's litres within 1 %.
3. **Per period** – an invoice clearly larger than one delivery takes the unmatched sessions between the previous such
   invoice and its bill date (aggregated invoices).
4. Sessions after the last invoice are "Not invoiced yet"; other sessions without an invoice and invoices without a
   session are exceptions.

**Columns:** Status, Match confidence (Confirmed, Inferred, Estimated or No match), Date, Supplier, Diesel sessions,
Session state, Session litres, Purchase Invoice, Supplier invoice no., Invoiced diesel litres, Physical diesel litres,
Delivery charge litres, Litre difference, Invoice gross, Invoice net, VAT, VAT %, Price VAT basis, Session projects,
Invoice projects, Allocation check (Consistent, Project conflict, Equipment conflict, Invoice has no project),
Evidence.

**Totals.** Tiles **Submitted session litres**, **Draft session litres**, **Invoiced physical diesel litres
(stated)**, **Invoiced litres estimated from amounts**, **Invoices**, **Exceptions** (red when any). Exception statuses
are shown in red.

**Access.** System Manager, Accounts Manager, whose roles also read Project Diesel Fill and Purchase Invoice.

## Related

- [Diesel](/card/features/diesel/)
- [Diesel API](/card/api-reference/diesel/)
- [Transport and cost reports](/card/reports/transport-costs/)
