---
title: Suppliers & Customers
description: The equipment supplier and customer registries, per-company figures, statements, summaries, the A4 supplier statement print and the settlement status of cards.
sidebar:
  order: 10
---

## Overview

CARD keeps a light registry of the parties it works with: **Card Equipment Supplier** (مورد المعدات) for the suppliers
whose machines are rented in, and **Card Equipment Customer** (عميل المعدات) for the customers to whom machines are
rented out. A registry row is only a pointer to the standard ERPNext Supplier or Customer. It stores **no totals**:
every figure is computed when it is shown, per company and only for the companies the user may see.

From these parties CARD produces **statements** (one party, one period) and **summaries** (all parties of a period),
and reconciles the card figures with what was actually invoiced through CARD and with the party's official ledger.

<!-- screenshot: suppliers-customers-registry -->

## Key concepts

| Concept | Meaning |
|---|---|
| Registry row | One row per ERPNext Supplier or Customer, named after it. Created and kept in sync when a card of that party is submitted or cancelled. |
| Supplier card | A submitted card of rented-in equipment (ownership other than «ملك» (Owned)) that bills the supplier. |
| Customer card | A submitted card whose direction bills a customer (rented out or sub-rental). |
| Net cards | Card amount + additions − deductions, before VAT (supplier side); *Total accrued (cards)* on the customer side. |
| Invoiced through Card | The card net billed by **submitted** CARD invoices, read from the posting trail, before VAT. |
| Not invoiced through Card | Net cards − invoiced through Card. A card inside a CARD draft invoice stays here until the invoice is submitted. |
| ERPNext invoices outside Card | The party's invoices that CARD did not build, shown for manual reconciliation; never matched to cards automatically. |

## Features

### Supplier and customer registries

- **Supplier** / **Customer** – the ERPNext party (the row's name); **Supplier name** / **Customer name** is read only.
- The older statistics fields (number of equipment, number of approved cards, total hours, totals, first and last
  month, last updated) are hidden and no longer stored, because one party-wide total mixed the figures of several
  companies.
- A rename of the ERPNext party renames its registry row; a merge drops the merged party's row and recomputes the
  surviving one.
- Change tracking cannot be turned on for the registries, because their old history holds figures of every company.

A user limited to some companies sees only the parties that have a draft or submitted card in one of those companies.

### Figures per company

Opening a registry row shows a **Figures per company** table, computed live from the submitted cards of that party in
the companies the user may see:

| Column | Content |
|---|---|
| Company | The company of the cards |
| Equipment | Number of distinct machines |
| Cards | Number of submitted cards |
| Operating hours | Total working hours |
| Net cards / Total accrued (cards) | Supplier net, or customer net amount |
| Period | First and last operating month |

The **Statement** button opens the party's statement for its last operating month (or the previous calendar month when
none is known), with the company pre-selected when the party works with one company only.

<!-- screenshot: suppliers-customers-figures -->

### Refresh numbers

`refresh_supplier` and `refresh_customer` re-sync one party (or every party with submitted cards) and are restricted
to **System Manager**. Because no figures are stored any more, a refresh only makes sure the registry row exists and is
named after its party.

:::note
If a registry sync fails while a card is submitted, the card is still saved and a message mentions a «Refresh
numbers» button. There is no such button on the form today; a System Manager can run the refresh through the API.
:::

### Equipment Supplier Statement

The **Equipment Supplier Statement** (كشف حساب المورد) groups monthly cards by **Project → Equipment → Card** for one
supplier and one period.

Filters: **Company**, **Statement type** («مورد» (Supplier) or «معدات ملك» (Owned equipment); the default comes from
Card Settings), **Supplier**, **From month / From year**, **To month / To year**, **Project**, **Equipment**,
**Equipment type**, **Include drafts** (default from *Include draft cards in reports*).

Columns include the description, equipment number and type, shift type, rate type, day billing basis, first and last
operation, working days, hours, rate, hourly rate, operating amount, additions, deductions and net.

Summary figures:

- **Number of equipment**, **Operating days**, **Operating hours**, **Net cards**;
- for users with General Ledger access: **Opening balance**, **Accrual entries (Credit)**, **Paid (Debit)**,
  **Supplier closing balance** from the supplier's GL entries (VAT included);
- **Invoiced through Card (net before VAT)**, **Not invoiced through Card**, and
  **ERPNext invoices outside Card — to reconcile (net before VAT)**.

The *Owned equipment* type lists the company's own machines by project with hours only (no money columns).

:::note
Ledger columns and tiles are removed on the server, not only hidden, for users without General Ledger access; the
statement then says that ledger balances are shown only to users with that access.
:::

### Equipment Customer Statement

The **Equipment Customer Statement** (كشف حساب العميل) is the customer-side mirror: cards that bill the customer
(rented out and sub-rental), grouped by project, equipment and card. Filters are the same without the statement type.
Ledger figures come from the customer's GL entries: **Opening balance**, **Invoiced entries (Debit)**,
**Received (Credit)**, **Customer closing balance**. CARD stores no customer balance, so these stay at zero until Sales
Invoices are posted.

### Suppliers and customers summaries

**Equipment Suppliers Summary** (ملخص الموردين) and **Equipment Customers Summary** (ملخص العملاء) list one row per
party with submitted cards in the period, without any registration step. Filters: company, period and project.

Columns: party code and name, equipment, cards, hours, operating days, net cards (or total accrued), invoiced and not
invoiced through Card, invoices outside Card, and for ledger readers the opening balance, accrual or invoiced entries,
paid or received and closing balance. Clicking a party name opens its statement. A difference between net cards and
invoiced through Card is highlighted.

### A4 statement print

The supplier statement has a standard report print format, **Equipment Supplier Statement A4**, pre-selected in the
print and PDF dialog:

- standard white print layout with the company name above the title;
- the statement details as label/value pairs, then the rows table and a totals table placed under the amount columns;
- the whole print in the user's language, with the page direction following it;
- the **Additions** and **Deductions** columns only when they are used;
- A4 page, with signature lines at the bottom.

The PDF is generated on the server from the report results with the user's own permissions, using the same layout as
the browser print, so Arabic text is shaped correctly.

<!-- screenshot: suppliers-customers-a4 -->

### Settlement status

**Card Settlement Status** (حالة تسوية الكروت) is a read-only report for **System Manager** and **Accounts Manager**.
Filters: **Company**, **Party type** (Supplier or Customer), **Party**, **From date**, **To date**.

For each submitted card of the party it shows the card net, the document that recognised it (**Recognised by** and
**Recognising document**), the **Card share of the document**, **Paid on the card**, **Credit notes and
adjustments**, **Remaining on the card** and the **Settlement status**:

| Status | Meaning |
|---|---|
| Not recognised yet | No CARD invoice, linked invoice or linked Journal Entry holds the card |
| Recognising document is a draft | The recognising invoice is not submitted |
| Ledger entry of the document not found | The document has no Payment Ledger row; it must be checked |
| Recognised, not settled | Recognised, nothing paid or adjusted yet |
| Partly settled | Part of the card's share is paid or adjusted |
| Fully settled | Nothing remains |

All amounts come from the Payment Ledger of the recognising document (VAT included for invoices). A document that
recognised several sources is shared by their amounts and its payments are allocated to the oldest source first.
Payments of the party not allocated to any document are shown apart; they are settled in ERPNext with Payment
Reconciliation, never in CARD.

## Workflow

1. Submit the month's cards; the supplier or customer registry row is created or synced automatically.
2. Open the registry row to see the figures per company, or press **Statement**.
3. Check **Not invoiced through Card** before the monthly posting, and again after the invoices are submitted (it
   should be zero).
4. Review **ERPNext invoices outside Card** for possible duplicates.
5. Print the supplier statement on A4 for signature.
6. Follow payments in **Card Settlement Status**.

## Permissions

| Item | Roles |
|---|---|
| Registries (read) | System Manager, Card Manager, Card User, Accounts Manager |
| Registries (create, write) | System Manager, Card Manager |
| Statements and summaries | System Manager, Card Manager, Card User, Accounts Manager |
| Ledger columns in statements and summaries | Users with General Ledger access |
| Card Settlement Status | System Manager, Accounts Manager |
| Refresh a registry | System Manager |

## Related

- [Monthly Cards](/card/features/monthly-cards/)
- [Invoicing & Posting](/card/features/invoicing-posting/)
- [Print Formats](/card/features/print-formats/)
- [Parties & statements reports](/card/reports/parties-statements/)
- [Parties & statements API](/card/api-reference/parties-statements/)
