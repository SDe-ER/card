---
title: "Diesel Dispense"
description: "Fields, layout and permissions of the Diesel Dispense DocType."
editUrl: false
sidebar:
  label: "Diesel Dispense"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/diesel-dispense` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Date | `date` | Date |  | Yes |
| Tank (From Warehouse) | `tank_warehouse` | Link | Warehouse | Yes |
| Project | `project` | Link | Project | Yes |
| Card Equipment | `card_equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |


**Quantity**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Dispensed Litres | `dispensed_litres` | Float |  | Yes |
| Notes | `notes` | Small Text |  |  |


**Evidence**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Evidence Attachment | `evidence_attachment` | Attach |  |  |


**System**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Stock Entry <small>(read only)</small> | `stock_entry` | Link | Stock Entry |  |
| Posting Key <small>(read only)</small> | `posting_key` | Data |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Diesel Dispense](/card/reference/doctypes/diesel-dispense/) |  |


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, submit, cancel, amend, report, export, print, email |
| Card User | read, write, create, report, print, email |
| Accounts Manager | read, report, export, print |
