---
title: "Card Stop Reason"
description: "Fields, layout and permissions of the Card Stop Reason DocType."
editUrl: false
sidebar:
  label: "Card Stop Reason"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/card-stop-reason` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Reason | `reason_name` | Data |  | Yes |
| Enabled | `enabled` | Check |  |  |
| Billable | `billable` | Check |  |  |
| Billable side | `billable_side` | Select | Both · Supplier · Customer |  |
| Billable approval reason | `billable_approval_reason` | Small Text |  |  |
| Default responsible party | `default_responsible_party_type` | Select | Company · Supplier · Customer · Other |  |
| Matching day status | `day_status` | Select | إجازة · عطل · توقف من العميل |  |

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Notes | `description` | Small Text |  |  |


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, report, export, print |
| Card Manager | read, write, create, report, export, print |
| Card Supervisor | read, report |
| Card User | read, report |
| Accounts Manager | read, report |
