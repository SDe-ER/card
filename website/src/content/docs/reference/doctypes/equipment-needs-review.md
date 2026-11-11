---
title: "Equipment Needs Review"
description: "Fields, layout and permissions of the Equipment Needs Review DocType."
editUrl: false
sidebar:
  label: "Equipment Needs Review"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/equipment-needs-review` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company <small>(hidden, read only)</small> | `company` | Link | Company |  |
| Project | `project` | Link | Project | Yes |
| From date | `from_date` | Date |  |  |
| To date | `to_date` | Date |  |  |
| Supervisor <small>(read only)</small> | `supervisor` | Link | User |  |
| Review submitted by <small>(read only)</small> | `submitted_by` | Link | User |  |
| Review edited by <small>(hidden, read only)</small> | `edited_by` | Small Text |  |  |
| Management approval <small>(read only)</small> | `approval_status` | Select | Pending · Approved |  |
| Approved by <small>(read only)</small> | `approved_by` | Link | User |  |
| Approved on <small>(read only)</small> | `approved_on` | Datetime |  |  |


**Lines**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Items | `items` | Table | [Equipment Needs Review Item](/card/reference/doctypes/equipment-needs-review-item/) |  |
| Notes | `notes` | Small Text |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Equipment Needs Review](/card/reference/doctypes/equipment-needs-review/) |  |


## Child tables

- [Equipment Needs Review Item](/card/reference/doctypes/equipment-needs-review-item/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Supervisor | read, write, create, submit, cancel, amend, report, print |
| Card User | read, report, print |
