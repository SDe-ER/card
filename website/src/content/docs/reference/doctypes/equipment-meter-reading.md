---
title: "Equipment Meter Reading"
description: "Fields, layout and permissions of the Equipment Meter Reading DocType."
editUrl: false
sidebar:
  label: "Equipment Meter Reading"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/equipment-meter-reading` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Equipment | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) | Yes |
| Company <small>(read only)</small> | `company` | Link | Company | Yes |
| Reading date and time | `reading_datetime` | Datetime |  | Yes |
| Engine hours | `engine_hours` | Float |  | Yes |
| Reading source | `source` | Select | Weekly reading · Handover reading · Service reading · Other reading | Yes |
| Previous reading <small>(read only)</small> | `previous_reading` | Data |  |  |
| Previous engine hours <small>(read only)</small> | `previous_engine_hours` | Float |  |  |
| Meter reset | `is_meter_reset` | Check |  |  |
| Reset reason | `reset_reason` | Small Text |  |  |


**Evidence**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Meter photo or document | `attachment` | Attach |  |  |
| Notes | `notes` | Small Text |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Equipment Meter Reading](/card/reference/doctypes/equipment-meter-reading/) |  |


## Permissions

| Role | Rights |
|---|---|
| Card Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Supervisor | read, write, create, submit, cancel, amend, report, print |
| Card User | read, report, print |
