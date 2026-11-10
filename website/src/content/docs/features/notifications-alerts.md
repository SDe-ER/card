---
title: Notifications & Alerts
description: The notifications CARD sends, the warnings it shows on forms, the audit trail of overrides and the alerts that are still planned.
sidebar:
  order: 19
---

## Overview

CARD informs users in three ways: **notifications** in the ERPNext notification bell (Notification Log), **warnings**
shown on a form when it is saved, and **comments** on a document's timeline for actions that must stay reviewable.
Notifications are off by default and switched on in Card Settings; warnings are advisory and never block a save,
unless a company rule is set to refuse.

<!-- screenshot: notifications-alerts-bell -->

## Key concepts

| Concept | Meaning |
|---|---|
| **Notification** | A Notification Log entry of type *Alert* for a user, shown in the Desk bell and linked to the document. |
| **Warning** | An orange message shown while saving a form. The record is saved; the warning asks for a review. |
| **Headline alert** | A coloured banner at the top of a form. |
| **Timeline comment** | An *Info* comment on the document, visible to everyone who can read it. |
| **Flag** | A mark on a record or line that asks a reviewer to look at it (never a refusal). |

## Features

### Notifications

Both notifications are set on the **Notifications** tab of [Card Settings](/card/getting-started/configuration/)
and are **off by default**. When a flag is off, CARD sends nothing.

| Setting | When | Who receives it | Content |
|---|---|---|---|
| **Notify on card submit** | A monthly card is submitted | The user who created the card | *Monthly operation card submitted: \<card\>* — card and equipment |
| **Notify on period lock override** | A user with the period lock override role creates, changes, submits, cancels or deletes a card, diesel fill or transport dated on or before the period lock date | Every user with the System Manager role | *CARD period lock override* — user, action, document, document date and lock date |

Administrator and Guest never receive CARD notifications. A failure to create one notification is logged and never
stops the action.

### Period lock override trail

Independently of the notification setting, every period lock override is:

- written to the server log of CARD, with the user, action, document, document date and lock date;
- added as a timeline comment on the document (*Period lock overridden by \<user\> on \<date\>: \<action\> with lock
  date \<date\>*), when the document already exists.

### Cancel reason

Cancelling a monthly card, an equipment transport or a project diesel fill asks for a reason. The reason is stored on
the cancelled record and added as a timeline comment with the user and the date.

### Warnings on monthly cards

Shown when a [monthly card](/card/features/monthly-cards/) is saved. The card is always saved; every recorded hour is
billed.

| Warning | When | Setting |
|---|---|---|
| Shift hours exceeded | Days with more hours than the shift limit (Max day-shift / night-shift hours) | Always |
| Days exceeding shift hours | Days with more hours than the equipment's daily hours | Warn when day hours exceed daily hours |
| Shift hours not set | The equipment has no daily hours, so the previous warning cannot appear | Warn when day hours exceed daily hours |
| Review rental period | Rented equipment worked outside its rental start and end dates, or has no rental start date | Warn when card dates fall outside rental period |
| Customer mismatch | The project's customer differs from the equipment's customer | Always |
| Downtime charge | A downtime charge names a stop reason that is also billable on the card's days, so the same downtime may be charged twice | Always |

### Warnings on equipment and movements

| Warning | Where | Behaviour |
|---|---|---|
| **Expired documents** / **Documents expiring within 30 days** | Card Equipment form | Red or orange headline alert listing registration, inspection, insurance and TÜV documents that expired or expire within 30 days |
| Equipment status Ended | New assignment, transport, monthly card or diesel fill for an equipment with status «منتهية» (Ended) | Warning with *Warn only*; refused with *Refuse* (company **Equipment status rule**) |
| Diesel fill project check | Diesel fill whose equipment is not assigned to the fill's project on its date | Warning with *Warn only* (default); refused with *Refuse*; nothing with *Off* (company **Diesel fill project check**) |
| Overlapping assignments | Updating an equipment's current location finds two or more assignments in force on the same day | Warning to the acting user, a comment on the equipment (and an Error Log entry from the daily job); the current project stays empty until the overlap is corrected |
| Equipment model cleared | The equipment type changed and the model no longer belongs to it | Message; the model is cleared |

### Flags for review

- **Repeated request** — an equipment needs line for an item already requested within the repeat window (Card
  Settings or company value, default 30 days) is flagged for the reviewer. It is never refused and never treated as a
  deduction.
- **Daily location sync** — when enabled in Card Settings, the daily job that sets each equipment's current project
  leaves a comment on the equipment whenever it overwrites a value.

### Scheduled jobs

CARD registers one daily job: the equipment location sync. It does nothing unless **Daily equipment location sync**
is switched on in Card Settings.

### Planned alerts

:::caution[Planned, not available yet]
- Daily alerts for draft monthly cards and for missing cards.
- Maintenance warnings by operating hours (service intervals per equipment type).
- Notifications in CARD Mobile.
:::

The deprecated setting **Notify on accounting posting** is hidden and has no effect.

## Permissions

| What | Who |
|---|---|
| Switch notifications on or off | Users who can write level 2 of Card Settings (System Manager) |
| Receive the period lock override notification | System Manager |
| Receive the card submit notification | The card's creator |
| See warnings and timeline comments | Every user who can open the document |

## Related

- [Configuration](/card/getting-started/configuration/)
- [Monthly cards](/card/features/monthly-cards/)
- [Equipment](/card/features/equipment/)
- [Roles & permissions](/card/features/roles-permissions/)
