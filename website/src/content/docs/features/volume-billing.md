---
title: Volume billing
description: Bill a customer per load and per cubic metre — loads x load volume x rate per m³, before VAT — on the equipment and the monthly card.
sidebar:
  order: 22
---

## Overview

Some machines are paid by the **load** rather than by the hour or the day: a truck takes a load from the crusher and
the customer pays for the volume it carried. CARD supports this as a **customer rate type** on the equipment. The
billed amount is the number of loads, times the load volume in cubic metres, times the rate per cubic metre, before
VAT. Hours are still recorded every day, for cost and productivity, but they are not billed on this basis.

The supplier side of a rented machine keeps its own rate basis (per day, per hour or per month). Volume billing only
changes the customer side.

## When to use it

- The customer agrees a price per m³ of material carried, and the number of loads is the record of the work.
- The machine is rented out to a customer, or is on a sub-rental where the customer side is billed per m³.
- You want the card to show loads and volume, so the statement and the print match what the customer will check.

Do not use it when the customer pays a day, an hour or a month rate. Those bases work as before.

## Worked example

A rented-out truck carries 40 loads in one working day. Each load is 16 m³ and the agreed price is 2 SAR per m³:

| Step | Value |
|---|---|
| Loads on the card | 40 |
| Load volume (per load) | 16 m³ |
| Total volume (40 × 16) | 640 m³ |
| Rate per m³ | 2 SAR |
| Customer amount, before VAT (640 × 2) | **1,280 SAR** |

Additions and deductions on the card are applied after this amount, as on every other basis. VAT is added later, on the
invoice, as it is for any sale; the card works with amounts before VAT.

## Equipment setup

On the equipment, in the **Customer** section:

1. **Customer rate type**: choose **Per m³** (stored as «بالمتر المكعب»). The other choices are per day, per hour and
   per month.
2. **Load volume (m³)**: the volume of one load. It is required when the rate type is per m³ and must be greater than
   zero. The equipment is refused on save without it.
3. **Customer rate**: the rate per m³ for day shifts.
4. **Customer rate (night shift)**: the rate per m³ for night shifts. When it is left empty or zero, night cards use the
   day rate.
5. **Reason for commercial change**: changing the load volume, the rate or the rate type of an existing equipment needs a
   new reason, as for every commercial term. Migrations and imports are exempt.

Only the customer side uses the per-m³ basis. The supplier rate and its basis are unchanged.

## Entering loads on the monthly card

On each day row of the monthly card:

- **Operating hours** are entered as before.
- **Loads** (number of loads on that day) is entered on a working day, that is a day whose status is working. A day
  with zero hours can still carry loads, because the day status decides and not the hours.
- Loads cannot be recorded on a day that is not a working day (leave, breakdown, client stop), and cannot be recorded
  for a future date. Future dates are refused for hours too.
- A negative number of loads is refused.

The card totals then show:

- **Total loads**: the sum of the loads on all day rows.
- **Total volume (m³)**: total loads × the load volume of the equipment.
- **Customer amount**: total volume × the customer rate (before VAT).

## Day and night cards

The shift of the card decides the rate:

| Card | Rate used |
|---|---|
| Day shift | Customer rate (per m³) |
| Night shift | Customer rate (night shift) when set; otherwise the customer rate |

A day card and a night card for the same equipment and project are separate documents, each priced on its own.

## Hours, stops and downtime

- Operating hours are recorded every day, for cost and productivity. On this basis they do not change the amount.
- A billable stop reason adds nothing to the customer amount on a per-m³ card. Stopped hours are still recorded as
  before, so the cost reports keep their meaning.
- Only loads and the load volume create the customer amount.

## Additions and deductions

Additions and deductions work as on every other card. They are applied to the customer side after the volume amount,
and the customer net before VAT is the customer amount plus the customer additions minus the customer deductions.

## Submitted cards keep their figures

When a card is submitted, CARD stores the figures it was priced with: the load volume used, the rate per m³ used, and
the totals. A later change to the equipment does not reprice a submitted card. The rate per m³ used is kept in the
field **Customer hourly rate used**, which for a per-m³ card holds the SAR per m³ rate, not an hourly rate. The field
**Rate basis used** holds the supplier rate basis; the customer basis is the card's **Customer rate type**.

## How volume billing appears

- **Monthly card print**: the print shows Total loads and Total volume (m³) for per-m³ cards, next to the rate and the
  total. Users without money read (for example Card Operator) get the print without any rate or amount column.
- **Customer statement**: a per-m³ row shows the basis, total loads, total volume, the rate per m³ and the amount. The
  row has no hourly rate and no hours-divided figure.
- **Dashboard**: two number cards on the CARD workspace show the loads and the volume of last month, from submitted
  per-m³ cards, for the companies the user may read.

## Permissions

- The loads, the volume and the totals are counts and volumes. The rate and the amount are money and keep their
  existing permission (Card User and Card Manager read them; Card Operator does not).
- The number cards read only submitted cards of the user's own companies. A user without read on monthly cards sees
  no value.
- No permission was widened to add this feature.

## Limitations

- **CARD Mobile** does not enter loads yet. Loads are entered on the Desk card.
- **Daily logs** do not carry loads yet. A draft card made from a daily log for a per-m³ equipment has no loads until
  they are entered on the card.
- No data migration is needed. Existing cards have no loads and keep their amounts.
- Arabic and the other interface languages use machine translations of the new labels until a native review is done.

## FAQ

**Why is the amount zero although hours were recorded?** On a per-m³ card the amount comes only from loads and the load
volume. Enter the loads on the day rows.

**Can I bill both hours and loads on the same card?** No. A card has one customer rate type. Use a separate equipment
or a separate card if the customer pays in two ways.

**What happens if the load volume changes after a card is submitted?** Nothing on that card. The submitted card keeps
the load volume it was priced with. The new volume applies to cards created after the change.

**Is the amount before or after VAT?** Before VAT. VAT is applied on the sales invoice like any other sale.

## Related

- [Equipment](/card/features/equipment/)
- [Monthly Cards](/card/features/monthly-cards/)
- [Print formats](/card/features/print-formats/)
- [Workspace & Dashboard](/card/features/workspace-dashboard/)
