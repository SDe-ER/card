---
title: "Employee Tool Custody"
description: "Fields, layout and permissions of the Employee Tool Custody DocType."
editUrl: false
sidebar:
  label: "Employee Tool Custody"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/employee-tool-custody` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company <small>(hidden, read only)</small> | `company` | Link | Company |  |
| Employee | `employee` | Link | Employee | Yes |
| Employee name <small>(read only)</small> | `employee_name` | Data |  |  |
| Movement | `movement` | Select | Handover · Return · Transfer · Loss · Damage | Yes |
| To employee | `to_employee` | Link | Employee |  |
| Date | `date` | Date |  | Yes |
| Tool | `item_code` | Link | Item | Yes |
| Tool name <small>(read only)</small> | `item_name` | Data |  |  |
| Quantity | `qty` | Float |  | Yes |
| Serial number | `serial_no` | Data |  |  |
| Store | `warehouse` | Link | Warehouse |  |


**Links**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Project | `project` | Link | Project |  |
| Equipment | `card_equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |
| Stock Entry <small>(read only)</small> | `stock_entry` | Link | Stock Entry |  |
| Needs review <small>(read only)</small> | `review_required` | Check |  |  |
| Notes | `notes` | Small Text |  |  |


**Handover confirmation**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Handover status <small>(read only)</small> | `handover_status` | Select | Awaiting handover · Handed over · Not handed over |  |
| Signed receipt | `handover_receipt` | Attach |  |  |
| Reason not handed over <small>(read only)</small> | `not_handed_reason` | Small Text |  |  |
| Confirmed by <small>(read only)</small> | `handed_by` | Link | User |  |
| Confirmed on <small>(read only)</small> | `handed_on` | Datetime |  |  |
| Equipment Needs Review <small>(read only)</small> | `review` | Link | [Equipment Needs Review](/card/reference/doctypes/equipment-needs-review/) |  |
| Review line <small>(hidden, read only)</small> | `review_item` | Data |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Employee Tool Custody](/card/reference/doctypes/employee-tool-custody/) |  |


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Stock Manager | read, write, create, submit, cancel, amend, report, print |
| Card Supervisor | read, write, create, submit, report, print |
| Card User | read, report, print |
