---
title: Parties and Statements
description: Supplier and customer statements, the supplier and customer summaries, and the card settlement status.
sidebar:
  order: 3
---

## Overview

These reports show what CARD owes its equipment suppliers and what its customers owe for rented-out equipment. The
**statements** list one party's monthly cards by project and equipment; the **summaries** give one row per party
with a link to its statement; **Card Settlement Status** follows each card into the ledger to show what is paid and
what remains.

CARD stores no party balance. Card figures come from the monthly cards; every balance comes from ERPNext's ledger
(**GL Entry** or **Payment Ledger Entry**) and is shown only to ledger readers (see
[Who can see money](/card/reports/overview/#who-can-see-money)).

## Key concepts

| Concept | Meaning |
|---|---|
| Supplier side | Cards of rented-in equipment and sub-rented equipment: «مستأجَرة من مورد» (Rented from a supplier) and «إيجار من الباطن» (Sub-rental). Their figure is the card **net**. |
| Customer side | Cards of «مؤجَّرة لعميل» (Rented to a customer) and «إيجار من الباطن» (Sub-rental). Their figure is the **customer net**. |
| Owned equipment statement | Statement type «معدات ملك» (Owned equipment): hours by project and equipment, without money. |
| Invoiced through CARD | The card net billed by **submitted** CARD monthly invoices for the cards shown (net before VAT). |
| Not invoiced through CARD | Card net minus invoiced through CARD. A card in a CARD draft invoice counts here until the invoice is submitted. |
| ERPNext invoices outside CARD | Submitted invoices of the party in the period that no submitted CARD posting points to (net before VAT). Shown for manual reconciliation, never matched to cards automatically. |
| Reconciliation tolerance | The Card Settings value below which a "Not invoiced through CARD" difference is shown green. |

## Equipment Supplier Statement

**Purpose.** One supplier's monthly cards (or the owned equipment's cards) grouped Project → Equipment → Card, and,
for a supplier, reconciled with the supplier's ledger: credits are accruals (liability up), debits are payments
(liability down).

<!-- screenshot: statements-supplier-statement -->

**Filters**

- **Company** – required.
- **Statement type** – «مورد» (Supplier) or «معدات ملك» (Owned equipment). When empty, the Card Settings default
  statement type is used.
- **Supplier** – shown for the supplier type; lists registry suppliers with cards in the company. Without a supplier
  the report shows "Select a supplier to display the statement."
- **From month**, **From year**, **To month**, **To year** – required; default to the previous month.
- **Project**, **Equipment**, **Equipment type** – optional.
- **Include drafts** – defaults to the Card Settings value **Include draft in reports**; draft cards are labelled
  "(Draft)".

Cards are selected by the month their period starts in. A supplier statement excludes owned equipment; an owned
statement includes only owned equipment.

**Columns:** Description (project, equipment or card number), Equipment number, Equipment type, Project, Shift type,
First operation, Last operation, Working days, Hours, and — when any row has a value — Billable stopped hours. A
supplier statement adds Rate type, Day billing basis, Rate, Hourly rate, Operating amount, Additions, Deductions,
Net. An equipment row with several rate types or bases shows «متعدد» (Multiple).

- Working days are the distinct days billed by operating hours or by billable stopped hours.
- The hourly rate is the amount divided by every billed hour (operating plus billable stopped hours).
- Additions and deductions are the supplier-side adjustments of each card.

**Totals.** Project and equipment rows total their children; a **Grand total** row closes the table. Summary tiles:
**Number of equipment**, **Operating days**, **Operating hours**; for a supplier also **Net cards**. A ledger reader
also sees **Accrual entries (Credit)**, **Invoiced through Card (net before VAT)**, **Not invoiced through Card**,
**ERPNext invoices outside Card — to reconcile (net before VAT)**, **Opening balance**, **Paid (Debit)** and
**Supplier closing balance** (opening + accruals − payments, VAT included).

**Access.** System Manager, Card Manager, Card User, Accounts Manager. Ledger tiles for ledger readers only.

**Print and PDF.** The **Equipment Supplier Statement A4** print format is pre-selected; the PDF action renders the A4
statement on the server (see [Print and PDF](/card/reports/overview/#print-and-pdf)).

## Equipment Suppliers Summary

**Purpose.** One row per supplier that has submitted, non-owned cards in the period, sorted by net (largest first),
with card totals and the ledger reconciliation. Clicking the supplier name opens the supplier's statement with the
same company, period and project.

**Filters:** **Company** (required), **From month / From year / To month / To year** (required, previous month by
default), **Project** (optional).

**Columns:** Supplier, Supplier code, Equipment, Cards, Operating days, Hours, (Billable stopped hours), Net cards,
Accrual entries, Invoiced through Card (net before VAT), Not invoiced through Card (red when not zero), ERPNext invoices
outside Card — to reconcile (orange when not zero), Opening balance, Paid, Closing balance. A **Total** row closes the
table.

**Totals.** Tiles **Number of suppliers**, **Net cards**, **Not invoiced through Card**, **ERPNext invoices outside
Card — to reconcile**, **Total supplier balances**.

**Access.** System Manager, Card Manager, Card User, Accounts Manager. For a non-ledger reader the ledger columns
(accruals to closing balance) and the three ledger tiles are removed on the server.

## Equipment Customer Statement

**Purpose.** The customer-side mirror of the supplier statement: one customer's billing cards (rented-out and
sub-rented) grouped Project → Equipment → Card, reconciled with the customer's receivable ledger: debits are invoices,
credits are receipts.

**Filters:** **Company** (required), **Customer** (registry customers with cards in the company; without one the
report asks to select a customer), **From month / From year / To month / To year** (required), **Project**,
**Equipment**, **Equipment type**, **Include drafts** (defaults to the Card Settings value).

**Columns:** Description, Equipment number, Equipment type, Project, Shift type, Period, First operation, Last
operation, Working days, Hours, (Billable stopped hours), Customer rate type, Day billing basis, Customer rate,
Hourly rate, Customer amount, Additions, Deductions, Net.

- A submitted card shows the hourly rate stored when it was submitted; a draft, or a card billed on a full-day basis,
  shows its amount over every billed hour.
- Additions and deductions are the customer-side adjustments.

**Totals.** Tree totals and a **Grand total** row. Tiles **Number of equipment**, **Operating days**, **Operating
hours**, **Total accrued (cards)**; for a ledger reader also **Invoiced entries (Debit)**, **Invoiced through Card (net
before VAT)**, **Not invoiced through Card**, **ERPNext invoices outside Card — to reconcile**, **Opening balance**,
**Received (Credit)** and **Customer closing balance**.

**Access.** System Manager, Card Manager, Card User, Accounts Manager.

## Equipment Customers Summary

**Purpose.** One row per customer with submitted billing cards in the period, sorted by accrued amount, with a link to
the customer's statement.

**Filters:** **Company**, **From month / From year / To month / To year** (required), **Project**.

**Columns:** Customer, Customer code, Equipment, Cards, Operating days, Hours, (Billable stopped hours), Total accrued
(cards), Invoiced entries, Invoiced through Card (net before VAT), Not invoiced through Card, ERPNext invoices outside
Card — to reconcile, Opening balance, Received, Closing balance; a **Total** row.

**Totals.** Tiles **Number of customers**, **Total accrued (cards)**, **Not invoiced through Card**, **ERPNext
invoices outside Card — to reconcile**, **Total customer balances**.

**Access.** System Manager, Card Manager, Card User, Accounts Manager; ledger columns and tiles removed for non-ledger
readers.

## Card Settlement Status

**Purpose.** For every submitted card of one party in the period: the document that recognised it (a CARD invoice, a
linked hand-booked invoice or a linked accrual journal entry), the card's share of that document, what is paid, what
other documents settled (credit notes, adjustments) and what remains. Every amount comes from ERPNext's **Payment
Ledger Entry** of the recognising document, so a cancelled or reconciled payment shows at once.

<!-- screenshot: statements-settlement-status -->

**Filters**

- **Company** – required.
- **Party type** – Supplier (default) or Customer.
- **Party** – optional; the user must be able to read it.
- **From date** / **To date** – required; default to the start of the year and today.

**Columns:** Card, Supplier / Customer, Month, Project, Equipment, Card net, Recognised by, Recognising document, Card
share of the document, Paid on the card, Credit notes and adjustments, Remaining on the card, Settlement status.

**Settlement status values**

| Status | When |
|---|---|
| Not recognised yet | No active posting log holds the card. |
| Recognising document is a draft | The holding posting is not submitted. |
| Ledger entry of the document not found | The document has no payment-ledger row; it must be checked (never shown as settled). |
| Recognised, not settled | Nothing is paid or otherwise settled. |
| Partly settled | Part of the share is paid or settled. |
| Fully settled | What remains is within 0.01. |

**Rules**

- A document's original amount is its own ledger row (invoice grand total, VAT included; accrual journal entry: the
  supplier credit).
- A document that recognised several sources is shared by their amounts; its settlement is allocated oldest source
  first, the last source taking the rounding rest.

**Totals.** Tiles **Cards net**, **Recognised share**, **Paid on the card**, **Credit notes and adjustments**,
**Remaining on the card**, and **Payments not allocated to a document up to the end date** (payments of the party
standing against themselves, to be settled in ERPNext with Payment Reconciliation).

**Access.** System Manager, Accounts Manager — ledger readers only; others are refused.

## Related

- [Suppliers and customers](/card/features/suppliers-customers/)
- [Invoicing and posting](/card/features/invoicing-posting/)
- [Adjustments](/card/features/adjustments/)
- [Accounting control reports](/card/reports/accounting-control/)
- [Parties and statements API](/card/api-reference/parties-statements/)
