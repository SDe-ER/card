---
title: "Card Daily Log"
description: "Fields, layout and permissions of the Card Daily Log DocType."
editUrl: false
sidebar:
  label: "Card Daily Log"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/card-daily-log` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Project | `project` | Link | Project | Yes |
| Daily log date | `log_date` | Date |  | Yes |
| Site supervisor | `supervisor` | Link | User |  |
| Daily log approval <small>(read only)</small> | `approval_status` | Select | Pending · Verified by supervisor · Approved · Returned for correction |  |
| Daily log submitted by <small>(read only)</small> | `submitted_by` | Link | User |  |
| Daily log edited by <small>(hidden, read only)</small> | `edited_by` | Small Text |  |  |
| Daily log verified by <small>(read only)</small> | `verified_by` | Link | User |  |
| Daily log verified on <small>(read only)</small> | `verified_on` | Datetime |  |  |
| Daily log approved by <small>(read only)</small> | `approved_by` | Link | User |  |
| Daily log approved on <small>(read only)</small> | `approved_on` | Datetime |  |  |
| Approved by its own preparer <small>(read only)</small> | `self_approved` | Check |  |  |
| Daily log return reason <small>(read only)</small> | `return_reason` | Small Text |  |  |
| Daily log returned by <small>(read only)</small> | `returned_by` | Link | User |  |
| Daily log returned on <small>(read only)</small> | `returned_on` | Datetime |  |  |


**Equipment hours**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Daily log equipment rows | `rows` | Table | [Card Daily Log Row](/card/reference/doctypes/card-daily-log-row/) | Yes |
| Notes | `notes` | Small Text |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Card Daily Log](/card/reference/doctypes/card-daily-log/) |  |


## Child tables

- [Card Daily Log Row](/card/reference/doctypes/card-daily-log-row/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, submit, cancel, amend, report, export, print, email |
| Card Supervisor | read, write, create, submit, cancel, amend, report, print |
| Card Operator | read, write, create, submit, cancel, amend, print |
| Card User | read, report, print |
