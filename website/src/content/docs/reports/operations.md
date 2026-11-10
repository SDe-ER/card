---
title: Operations Reports
description: Location history, downtime, meter reconciliation, consumption, equipment needs, repeat requests and worker custody.
sidebar:
  order: 2
---

## Overview

The operations reports answer day-to-day questions about the fleet: where a machine was, why it stood still, whether
its hour meter is believable, what it consumed, what the sites ask for and which tools each worker holds. All of them
are read-only and follow the common rules of the [reports overview](/card/reports/overview/).

## Key concepts

| Report | Main source | Company filter |
|---|---|---|
| Equipment Location History | Card Equipment, Card Equipment Assignment, Equipment Transport | One company (required) |
| Equipment Downtime | Card Monthly Card day rows | One company (required) |
| Equipment Meter Reconciliation | Asset hour-meter readings, Card Monthly Card hours | One company (required) |
| Equipment Consumption | Stock Entry (Material Issue), Purchase Invoice lines | All permitted companies |
| Equipment Needs Summary | Equipment Needs Review lines | All permitted companies |
| Repeat Equipment Requests | Equipment Needs Request lines | All permitted companies |
| Worker Custody | Employee Tool Custody, Asset (custodian) | All permitted companies |

## Equipment Location History

**Purpose.** For one company, an optional machine and a period, shows where each machine was, in date-aware segments:
a project assignment, the place an approved transport sent it to (workshop, storage or supplier), or the company's
initial place. A move to a workshop, storage or supplier on day T shows the project on T and the new place from T+1.

<!-- screenshot: operations-location-history -->

**Filters**

- **Company** – required.
- **From date** / **To date** – required; default to the current month.
- **Equipment** – optional; limited to equipment of the chosen company.

**Columns:** Equipment, From date, To date, Location type (Project, Workshop, Storage, Supplier or Initial place),
Location (the project name for a project segment), Project, Overlapping projects (check), Source type, Source
document.

**Totals and messages.** No totals. When a machine is on two projects on the same days, the rows are marked as
overlapping and the report says so in its message.

**Access.** System Manager, Card Manager, Card User, Accounts Manager. The user's roles must also read Card Equipment,
Card Equipment Assignment and Equipment Transport; an equipment of another company is refused, never read.

**Notes.** The end date may not be before the start date. The initial place covers the time before the first move.

## Equipment Downtime

**Purpose.** The stopped days and hours of one company's monthly cards in a period. A downtime row is a card day with a
stop reason, stopped hours, or a non-working day status; an older day without a reason is shown under its day status,
so earlier months are not lost.

<!-- screenshot: operations-equipment-downtime -->

**Filters**

- **Company** – required.
- **From date** / **To date** – required; default to the start of the month and today.
- **Group downtime by** – Stop reason (default), Responsible party, Equipment, Project, Month, or Each day.
- **Project**, **Equipment** – optional.
- **Stop reason** – optional, limited to the company's **Card Stop Reason** records.
- **Responsible party** – optional: Company, Supplier, Customer or Other.
- **Include draft cards** – off by default (submitted cards only).

**Columns (grouped views):** the group (Stop reason, Responsible party, Equipment — with Equipment name —, Project or
Month), Stopped days, Full stopped days, Stopped hours, Billable stopped hours, Equipment count.

**Columns ("Each day"):** Date, Card, Equipment, Equipment name, Project, Day status, Stop reason, Stopped hours,
Billable stopped hours, Operating hours, Responsible party, Responsible party record, Idle reason, Draft card.

**Totals.** Summary tiles **Stopped days**, **Stopped hours** and **Billable stopped hours**; the standard total row is
enabled. Stopped hours count as billable only under a stop reason marked billable.

**Access.** System Manager, Card Manager, Card User, Accounts Manager, with read on Card Monthly Card. Only the cards the
user may read are counted.

## Equipment Meter Reconciliation

**Purpose.** Checks the cumulative hour-meter readings of each machine and compares the meter hours with the hours of
its submitted monthly cards. Only the difference between two consecutive plausible readings counts as hours. It sets
no maintenance baseline and changes nothing.

**Filters**

- **Company** – required.
- **Equipment** – optional.
- **View** – "One row per equipment" (default) or "Every reading".
- **Show** – "Needs review only" (default) or "All equipment" (summary view only).
- **Allowed difference %** – default 10.

**Columns (one row per equipment):** Status (Consistent, Needs review, No meter readings), Equipment, Equipment name,
Asset, Meter readings, First plausible reading, First reading date, Last plausible reading, Last reading date, Meter
hours (differences only), CARD hours (submitted cards, same period), Difference %, Reading issues, Asset meter fields,
Maintenance baseline.

**Columns (every reading):** Equipment, Asset, Reading time, Meter reading, Hours since previous plausible reading,
Reading check, Source, Source record, Evidence.

Each reading is classified as Plausible, Invalid (zero, negative or empty), Duplicate, Backward, Meter reset (restarts
near zero), Impossible jump (more hours than elapsed time), or "Recorded hours equal the whole meter (cumulative):
ignored". A row needs review when a reading has an issue, when the Asset's own meter fields differ from the last
plausible reading by more than the allowed percentage, when CARD hours differ from the meter hours by more than the
allowed percentage, or when the Asset ID conflicts with its name or item.

**Totals.** Tiles **Equipment** and **Needs review** (summary view) or **Readings** (detail view). The message
restates the maintenance policy (alert at 250 operating hours, oil change due at 300).

**Access.** System Manager, Card Manager, Accounts Manager, whose roles also read Card Equipment, Card Monthly Card and
Asset. Readings are read from a legacy fuelling log DocType when one exists on the site and the user may read it;
otherwise the message says none are available.

## Equipment Consumption

**Purpose.** What each machine actually consumed: stock issued to it (submitted **Stock Entry** of purpose Material
Issue) plus non-stock items bought and used at once (submitted **Purchase Invoice** lines of non-stock items). The
purchase of a stock item is never counted — its cost comes with the issue — so nothing is counted twice.

**Filters:** **From date**, **To date**, **Project**, **Equipment** (all optional).

**Columns:** Equipment, Project, Item, Quantity, Cost (in the row's own company currency), Source (the Stock Entry or
Purchase Invoice), Date.

**Totals.** None.

**Access.** System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager. Rows come from
every company the user may see for Card Equipment.

**Notes.** Lines are attributed through the **Card Equipment** accounting dimension; without it on the site the report
says so and lists nothing.

## Equipment Needs Summary

**Purpose.** The consolidated list management reviews: every line of the submitted **Equipment Needs Review** records,
merged by item, keeping each machine's share.

**Filters**

- **Project** – optional.
- **Management approval** – Pending (default), Approved or empty for both.

**Columns:** Needed item, Description, Requested qty, Found on site, Approved qty, In stock, Equipment and quantities
(for example `EQ-0001: 2, EQ-0002: 1`), Reviews.

**Totals.** None.

**Access.** System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager. The user's own
record rules apply to the reviews (for example a supervisor limited to his projects).

**Notes.** **In stock** is read live in the warehouses of the report's companies, only for a user who may read stock;
for anyone else the column is removed.

## Repeat Equipment Requests

**Purpose.** Items asked again for the same machine within the repeat window set in Card Settings (or the company's
own value). It is a list to review, never a penalty or a deduction.

**Filters:** **Project**, **Equipment** (optional).

**Columns:** Request, Date, Equipment, Operator name, Item, Quantity, Last asked on.

**Totals.** None.

**Access.** System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager; only submitted
requests the user may read are listed.

## Worker Custody

**Purpose.** What each worker holds now: returnable tools from the custody register (balance of submitted Handover,
Return and Transfer movements) plus capital tools recorded as submitted **Assets** with the worker as custodian
(scrapped and sold assets excluded).

**Filters:** **Employee** (optional).

**Columns:** Employee, Employee name, Tool, Held, Asset, Kind ("Returnable tool" or "Asset").

**Totals.** None.

**Access.** System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager, across every
company the user may see for Employee Tool Custody.

## Related

- [Reports overview](/card/reports/overview/)
- [Assignments and locations](/card/features/assignments-locations/)
- [Meter readings](/card/features/meter-readings/)
- [Equipment needs](/card/features/equipment-needs/)
- [Tool custody](/card/features/tool-custody/)
