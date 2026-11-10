---
title: Additions & Deductions
description: Configured addition and deduction types per company, their use on monthly cards, VAT treatment and the ZATCA guards of the monthly posting.
sidebar:
  order: 8
---

## Overview

Additions and deductions adjust the amount of a monthly card: a mobilisation charge, a late-arrival deduction, a
downtime charge agreed with the customer. Each company configures its own **addition/deduction types** in Card
Settings. A type says whether it adds or deducts, which account its invoice line posts to, and whether it is taxable.
On the card, each row names its type and the side it belongs to – the supplier's invoice or the customer's.

When the month is posted, every typed row becomes its own line on the draft Purchase or Sales Invoice, under rules
that keep customer invoices valid for ZATCA e-invoicing (no negative lines).

<!-- screenshot: adjustments-card-table -->

## Key concepts

| Concept | Meaning |
|---|---|
| Card Adjustment Type | A row of the **Addition/Deduction Types** table in Card Settings, one company per row. |
| Kind | «إضافة» (Addition) or «خصم» (Deduction). |
| Taxable | On: the line carries the company's VAT rate (for example 15%). Off: the 0% template. |
| Side | Supplier (Purchase Invoice) or Customer (Sales Invoice). |
| Downtime charge | A type flagged as a charge for downtime; its rows must name the stop reason, responsible party and agreement reference. |

## Features

### Card Adjustment Type

Configured in **Card Settings → Addition/Deduction Types**.

| Field | Rules |
|---|---|
| Company | Required. A type belongs to one company. |
| Type name | Required; unique per company. |
| Kind | «إضافة» (Addition) or «خصم» (Deduction); required. |
| Account | Required. Expense account (supplier side) or income account (customer side) of the invoice line; must be an enabled leaf account of the row's company. |
| Taxable | Default on. Taxable lines carry the VAT item tax template at the rate of the company's tax templates; non-taxable lines carry the 0% template. |
| Item | Read only. A non-stock service item created for the type on the first posting. |
| Downtime charge | Default off. See below. |
| Disabled | Default off. A disabled type cannot be used on a card. |

A company-restricted user sees and changes only the types of their own companies.

### Additions and deductions on a card

The **Additions and deductions** table of a monthly card:

- **Adjustment type** – the configured type's name for the card's company; it sets **Type** (Addition / Deduction)
  from the type's kind. Older rows without a type keep working and count on the supplier side.
- **Description** and **Amount** – required; the amount must be greater than zero (the kind gives the sign).
- **Side** – Supplier or Customer. Empty takes the card's billed side (Customer for a card rented to a customer,
  Supplier otherwise). A sub-rental card bills both parties, so every row must choose its side.
- A typed customer-side row needs a card with a customer; a typed supplier-side row needs a card with a supplier.

Each side adds its own rows to its own total:

- **Net due** = Total amount + supplier-side additions − supplier-side deductions;
- **Customer net amount** = Customer amount + customer-side additions − customer-side deductions.

**Total additions** and **Total deductions** show the sums of both sides together.

Rows are changed only through the card's own save, so every change is validated and kept in the card's history. A
direct update of a row's amount, type, side or downtime fields (REST, `frappe.client`) is refused, and a row cannot be
moved to another card.

### Downtime charges

A type with **Downtime charge** on is the explicit, audited way to charge for downtime. Each card row of such a type
must name:

- a **Stop reason** – an enabled stop reason of the card's company;
- the **Responsible party** – Company (always the card's company), Supplier, Customer (with the record) or Other (with
  a name);
- the **Agreement reference** – the agreement under which the charge is made.

On any other row these fields are optional, but a stop reason given there must still belong to the card's company.
When a downtime charge names a stop reason that is also billable through the card's days on the same side, the card
warns that the same downtime may be charged twice.

### ZATCA guards in the monthly posting

When the monthly draft invoices are built (see [Invoicing & Posting](/card/features/invoicing-posting/)):

| Situation | Result |
|---|---|
| Supplier-side addition | A positive line on the Purchase Invoice with the type's item and account. |
| Supplier-side deduction | A negative line on the Purchase Invoice. |
| Customer-side addition | A positive line on the Sales Invoice; taxable or 0% by the type. |
| Customer-side **taxable** deduction | No negative line: it becomes a discount on the invoice Net Total, which lowers the VAT base by the same amount. |
| Customer-side **non-taxable** deduction | Refused: it cannot be shown as a Net Total discount without changing the VAT base. |
| Customer with a zero-rated addition and a deduction discount in the same month | Refused: the discount would spread over the zero-rated line. Post them in separate months. |
| Monthly total of a party below zero | Refused: deductions exceed the dues; correct the cards first. |
| Row with a type that is missing or disabled | Refused until the type is configured or enabled again. |

The VAT rate of taxable lines is read from the company's own purchase and sales tax templates; nothing hardcodes the
rate.

### Deduction limits and approval tier

Per-company limits on deductions with an approval tier computed by the server are **planned**. Today any user who may
edit a card can add a deduction of any positive amount; the card's submit and the posting review are the controls.

## Workflow

1. In Card Settings, add the company's addition and deduction types with their accounts and tax treatment.
2. On a monthly card, add a row: pick the type, write the description and the amount, choose the side.
3. For a downtime charge, fill the stop reason, responsible party and agreement reference.
4. Save and check **Net due** and **Customer net amount**; submit the card.
5. The monthly posting turns each row into an invoice line or a discount under the rules above.

## Permissions

| Action | Who |
|---|---|
| Configure types in Card Settings | System Manager and Accounts Manager (Card Manager can read); a company-restricted user only for their own companies |
| Add rows on a draft card | Users who may edit the card (Card User, Card Manager, System Manager) |
| Submit the card | Card Manager, System Manager |
| Build the monthly posting | Card Manager, System Manager |

## Related

- [Monthly Cards](/card/features/monthly-cards/)
- [Invoicing & Posting](/card/features/invoicing-posting/)
- [Suppliers & Customers](/card/features/suppliers-customers/)
- [Configuration](/card/getting-started/configuration/)
