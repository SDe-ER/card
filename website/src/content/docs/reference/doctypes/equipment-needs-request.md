---
title: "Equipment Needs Request"
description: "Fields, layout and permissions of the Equipment Needs Request DocType."
editUrl: false
sidebar:
  label: "Equipment Needs Request"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/equipment-needs-request` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company <small>(hidden, read only)</small> | `company` | Link | Company |  |
| Equipment | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) | Yes |
| Equipment name <small>(read only)</small> | `equipment_name` | Data |  |  |
| Project <small>(read only)</small> | `project` | Link | Project |  |
| Operator | `operator` | Link | Employee | Yes |
| Operator name <small>(read only)</small> | `operator_name` | Data |  |  |
| Date | `request_date` | Date |  | Yes |
| Entered by <small>(read only)</small> | `entered_by` | Link | User |  |
| Entered on behalf <small>(read only)</small> | `on_behalf` | Check |  |  |
| Review status <small>(read only)</small> | `review_status` | Select | Pending · In review · Approved · Rejected |  |


**Needs**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Items | `items` | Table | [Equipment Needs Request Item](/card/reference/doctypes/equipment-needs-request-item/) | Yes |
| Notes | `notes` | Small Text |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Equipment Needs Request](/card/reference/doctypes/equipment-needs-request/) |  |


## Child tables

- [Equipment Needs Request Item](/card/reference/doctypes/equipment-needs-request-item/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Supervisor | read, write, create, submit, cancel, amend, report, print |
| Card Operator | read, write, create, submit, print |
| Card User | read, report, print |
