---
title: Monthly Cards
description: The monthly operating card of one machine on one project and shift — days, hours, downtime, rates, additions, deductions and totals.
sidebar:
  order: 6
---

## Overview

The **Card Monthly Card** (كارت التشغيل الشهري) is the core document of CARD. It records, for one machine, one project,
one month and one shift, what the machine did each day: operating hours, the day status, downtime with its stop
reason and responsible party, and notes. From those days and the rates on the equipment, the card computes what is
owed to the supplier of a rented machine, what is billed to the customer of a machine rented out, or both on a
sub-rental, then applies additions and deductions to reach the net amounts.

A submitted card is the source for the supplier and customer statements and for the monthly draft Purchase and Sales
Invoices (see [Invoicing & Posting](/card/features/invoicing-posting/)). The card never writes ledger entries itself.

<!-- screenshot: monthly-cards-form -->

## Key concepts

| Concept | Meaning |
|---|---|
| One card per key | Equipment + project + month + year + shift. A second live card with the same key is refused. |
| Shift | «نهاري» (Day) or «ليلي» (Night). Day and night cards are separate documents, each priced on its own. |
| Card direction | Mirrored from the equipment's rental direction; decides which side(s) the card bills. |
| Supplier side | `Total amount` and `Net due`: the cost of a machine rented from a supplier. |
| Customer side | `Customer amount` and `Customer net amount`: the billing value of a machine rented to a customer. |
| Rate basis | Per hour, per day or per month, from the equipment. |
| Billable stop | Stopped hours of a stop reason that is explicitly billable; they are billed like operating hours. |
| Snapshot | Values stored at submit so a submitted card never follows later changes to the equipment or settings. |

## Features

### Header fields

The **Card details** section:

- **Equipment** – required; the company is taken from the equipment and cannot differ from it.
- **Project** – required; resolved from the machine's approved transports for the month (see below).
- **Shift type** – «نهاري» (Day) or «ليلي» (Night); empty takes the **Default shift** of Card Settings.
- **Month** and **Year** – required; **From date** and **To date** are set to the first and last day of the month.
- **Location**, **Equipment name**, **Ownership**, **Owner** (supplier) – filled from the equipment.
- **Driver / Operator** – the external operator's name, or **Operator** (an Employee) when the machine is owned or the
  company provides the operator.

The **Equipment information** section shows the direction, customer, customer rate type and rate, the day billing
basis and the values used at submit.

### Numbering by operating month

Cards are named `EOMC-{year}-{month}-{####}`, for example `EOMC-2026-10-0001`. The year and month are the card's
operating month, not the date it was created, so a card entered later for an earlier month is still numbered under
that month.

### Project from approved transports

When the user picks the equipment, month and year, the form asks the server which projects the machine's approved
transports put it on that month and builds one day row for each day the machine was on that project.

- One project: it is set automatically.
- Several projects (the machine moved during the month): the user chooses one; each project gets its own card.
- No approved transport that month: the card is refused until an Equipment Transport records the move.
- A project the machine was not on that month is refused, also through the API.
- Days the machine was a component of a unit belong on the unit's card, not the component's.

Changing the month or year on a card that already has day rows asks before rebuilding the days, because the recorded
hours would be cleared.

### Card direction and billed sides

**Card direction** (`card_direction`) is read live from the equipment until submit.

| Direction | Stored value | Supplier side | Customer side |
|---|---|---|---|
| Rented from supplier | «مستأجَرة من مورد» | Yes | No |
| Rented to customer | «مؤجَّرة لعميل» | No | Yes |
| Sub-rental | «إيجار من الباطن» | Yes | Yes |
| Internal operation | «تشغيل داخلي» | No | No |

An owned machine («ملك») may only run internally or be rented out; any other ownership is rented in or sub-rented.
A card that bills a customer cannot be submitted until the equipment carries the customer. When the project's customer
differs from the equipment's customer, the card warns but does not block.

### Days table

The **Days of month** table has one row per date.

| Field | Meaning |
|---|---|
| Date | Required; must lie inside the card's month and appear only once. |
| Day | Day name, set by the form. Fridays are shaded in the grid. |
| Day status | «عمل» (Working), «إجازة» (Day Off), «عطل» (Breakdown), «توقف من العميل» (Stopped by Customer). Default Working. |
| Operating hours | Hours worked. Any status other than Working sets them to 0. |
| Idle reason | Free text. |
| Stop reason | Optional link to an enabled **Card Stop Reason** of the card's company. |
| Stopped hours | Hours the machine stood still. |
| Billable stop | Read only: whether this row's stopped hours are billed (a snapshot of the reason when saved). |
| Responsible party | Company, Supplier, Customer or Other; empty takes the stop reason's default. |
| Responsible party record / name | The record for Company, Supplier or Customer; a free-text name for Other. |
| Notes | Free text (a day generated from a daily log names that log here). |

Rules on save:

- no operating or stopped hours on a future date;
- operating hours plus stopped hours cannot exceed 24 on a day that has stopped hours;
- every day with hours must fall inside an assignment period of the machine on the card's project (every component
  for a unit);
- a day over the shift limit (**Max day-shift hours** / **Max night-shift hours**, default 12) only **warns**: every
  recorded hour is billed and the day is listed for review;
- with **Warn when day hours exceed daily hours** on, days above the equipment's daily working hours are listed;
- with **Warn when card dates fall outside rental period** on, operating days outside the rental start/end of a rented
  machine are listed;
- a Company responsible party must be the card's company; a supplier or customer that is not the card's own is
  flagged for review.

### Downtime and stop reasons

Downtime is recorded per day with a **Card Stop Reason**, a per-company master (reason, enabled, billable, billable
side, billable approval reason, default responsible party, matching day status).

- A reason is **not billable** by default: its stopped hours earn no rental.
- A billable reason bills its stopped hours like operating hours, on its **Billable side**: Both, Supplier or
  Customer. A side the card does not bill ignores it. Switching billing on, or changing the side, needs a
  **Billable approval reason**.
- A day billed only by billable stopped hours (no operating hours) counts as a billed day.
- On a sub-rental card, a one-sided billable reason is flagged: the other side's amount does not include those hours.

The totals keep **Billable stopped hours**, **Billable stopped days**, and the per-side **Supplier billable stopped
hours** and **Customer billable stopped hours**.

:::tip
The recommended route to charge for downtime is a downtime-charge addition (see
[Additions & Deductions](/card/features/adjustments/)). When a downtime charge names a stop reason that is also billed
through the days on the same side, the card warns that the same downtime may be charged twice.
:::

### Rate bases

The rate and its basis come from the equipment: **Rate type** and **Rate** for the supplier side, **Customer rate
type** and **Customer rate** for the customer side.

| Basis | Stored value | Hourly rate used |
|---|---|---|
| Per hour | «بالساعة» | rate |
| Per day | «باليوم» | rate ÷ equipment **Daily working hours** |
| Per month | «بالشهر» | rate ÷ **Standard month hours** (Card Settings, default 260 = 26 days × 10 h) |

Every recorded hour is billed; there is no minimum and no cap. A supplier-billing card without a rate basis, or a
per-day rate without daily hours, is refused.

### Full-day versus prorated day billing

For a per-day rate, the equipment's **Day billing basis** decides how days become an amount:

- **Prorated by hours** (default): billed hours × (rate ÷ daily hours).
- **Full day**: billed days × rate, whatever the hours of each day. Billed days are operating days plus days billed
  only by billable stopped hours of that side.

The basis applies to each side by its own rate basis (an hourly or monthly side is not affected) and is shown on the
card as **Day billing basis** and, after submit, **Day billing basis used**.

### Day and night cards; night customer rate

Day and night shifts are separate cards with their own days and totals. A night card of a customer-billing machine
uses the equipment's **Customer rate (night shift)** when it is set; otherwise the normal customer rate. The supplier
rate is the same for both shifts. Under "Full day", each shift card bills its own full day.

### Additions and deductions

The **Additions and deductions** table adds or deducts amounts per side:

- **Type** – «إضافة» (Addition) or «خصم» (Deduction); a configured type sets it.
- **Description** and **Amount** – required; the amount must be greater than zero.
- **Adjustment type** – a type configured for the card's company in Card Settings.
- **Side** – Supplier or Customer; empty takes the card's billed side; a sub-rental card requires a choice.
- **Stop reason**, **Agreement reference**, **Responsible party** – required for a downtime charge.

Rows are changed only through the card itself; a direct row update is refused. Details:
[Additions & Deductions](/card/features/adjustments/).

### Totals

| Field | Calculation |
|---|---|
| Working days | Days with operating hours. |
| Total operating hours | Sum of operating hours. |
| Total amount | Supplier side: billed hours × hourly rate, or billed days × day rate under "Full day". 0 when the card bills no supplier. |
| Total additions / Total deductions | Sums over all rows of both sides. |
| Net due | Total amount + supplier-side additions − supplier-side deductions. |
| Customer amount | Customer side, computed like the supplier side with the customer rate. 0 when the card bills no customer. |
| Customer net amount | Customer amount + customer-side additions − customer-side deductions. |

The form shows a live preview of the totals; the server recalculates everything on save.

### Worked example

Fictitious data: **EQ-0001** on **PROJ-0001**, day shift, sub-rental from **Supplier A** to **Example Contracting Co.**
Supplier rate «باليوم» 2,500 per day, daily working hours 10, so the hourly rate is 250. Customer rate «بالساعة» 300.

| Days | Day status | Operating h | Stop reason | Stopped h |
|---|---|---|---|---|
| 24 days | Working | 10 each = 240 | – | – |
| 1 day | Working | 6 | – | – |
| 1 day | «عطل» (Breakdown) | 0 | Breakdown (not billable) | 10 |
| 1 day | «توقف من العميل» (Stopped by Customer) | 0 | Waiting for customer (billable, Both) | 8 |

- Working days 25, total operating hours 246, billable stopped hours 8, billable stopped days 1.
- **Prorated by hours:** (246 + 8) × 250 = **63,500** Total amount.
- **Full day** (same card, if the equipment used it): (25 + 1) × 2,500 = **65,000**.
- Supplier-side rows: addition 500, deduction 1,500 → **Net due** 63,500 + 500 − 1,500 = **62,500**.
- Customer side: (246 + 8) × 300 = **76,200** Customer amount; customer-side addition 1,000 → **Customer net amount
  77,200**.

The breakdown day's 10 hours earn nothing because its reason is not billable.

### Meter readings, overtime, quantity and standby billing

These are **not** part of the monthly card today:

- overtime hours, meter readings per shift, quantity / cubic-metre billing, standby and lump-sum billing and a
  Billing Basis master existed in an older generation of the app and are not in the current code;
- engine-hour readings are kept in a separate document (see [Meter Readings](/card/features/meter-readings/));
- a rate per quantity unit can be recorded on a [rate agreement](/card/features/rate-agreements/), but no card
  uses it yet.

### Submission and snapshot

On submit the card stores the values it was priced with: **Daily hours (used)**, **Hourly rate (used)**, **Fuel
charged to (used)**, **Customer hourly rate used**, **Direction used**, **Customer used**, **Rate basis used** and
**Day billing basis used**. A later change to the equipment or Card Settings never reprices a submitted card. The
supplier and customer registries are refreshed, and with **Notify on card submit** on, the card's owner is notified.

### Review, approval and separation of duties

A card has the standard states Draft → Submitted → Cancelled. CARD ships no approval workflow for monthly cards:

- whoever may submit a card (Card Manager, System Manager) submits it directly;
- an enforced rule that the person who entered a card never approves it is **planned**;
- a review step with "return with reason" is **not available** on monthly cards today. Use the
  [daily log](/card/features/daily-logs/) approval, which does separate the preparer from the approver, to check the
  hours before they reach a card.

### Cancel reason and amendment

- Cancelling needs a **Cancel Reason**. The form's Cancel asks for it; a REST cancel must send it. The reason is stored
  on the card and in a comment with the user and date, and cannot be edited afterwards.
- A cancel request that changes any other field or row is refused.
- A card held by a draft or submitted posting cannot be cancelled until that posting is cancelled.
- A cancelled card can be amended into a new draft; an amended copy of a posted card is refused unless its posting was
  cancelled.
- Bulk cancel from the list view is refused: cancel each card from its form.

### Period lock

With a **Period lock date** set in Card Settings (Period Lock tab), a card whose period ends on or before that date
cannot be saved, submitted, amended, cancelled or deleted. Both the stored and the new date are checked, so a card
cannot be moved out of or into the locked period. A user with the **Period lock override role** may proceed; every
override is logged, commented on the card and, with **Notify on period lock override** on, notified to System
Managers.

Cards may also be back-entered only within the **current fiscal year**.

### Payments

The card does not record payments and does not create Payment Entries. Payments are made in ERPNext against the
invoices CARD prepares; the settlement status of each card is shown in the reports (see
[Parties & Statements](/card/reports/parties-statements/)).

### Money visibility

Today every user who can read a card sees its amounts. Restricting card amounts to authorised roles is **planned**.
The internal operating rate of owned equipment is already restricted on the equipment record.

## Workflow

1. Record the machine's move with an approved Equipment Transport (this creates the assignment).
2. Create the card: pick the equipment, month, year and shift; the project and the eligible days fill in.
3. Enter the hours per day (or generate them from approved daily logs), with stop reasons where the machine stood.
4. Add additions and deductions, with the side and type.
5. Save, review the warnings and the totals, then submit.
6. The submitted card appears in the statements and is picked up by the monthly posting.

## Permissions

| Role | Rights on monthly cards |
|---|---|
| Card User | Create, edit, read, print, report (cannot submit or cancel) |
| Card Manager | Create, edit, submit, cancel, amend |
| System Manager | All, including delete |
| Accounts Manager | Read, print, report, export |

Company User Permissions apply: a card's company is always its equipment's company, and a restricted user can
neither create nor move a card into another company.

## Related

- [Daily Logs](/card/features/daily-logs/)
- [Rate Agreements](/card/features/rate-agreements/)
- [Additions & Deductions](/card/features/adjustments/)
- [Invoicing & Posting](/card/features/invoicing-posting/)
- [Suppliers & Customers](/card/features/suppliers-customers/)
- [Print Formats](/card/features/print-formats/)
