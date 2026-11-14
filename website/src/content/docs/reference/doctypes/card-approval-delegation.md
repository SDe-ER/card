---
title: "Card Approval Delegation"
description: "Fields, layout and permissions of the Card Approval Delegation DocType."
editUrl: false
sidebar:
  label: "Card Approval Delegation"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/card-approval-delegation` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Delegator (grantor) | `delegator_user` | Link | User | Yes |
| Delegate (grantee) | `delegate_user` | Link | User | Yes |
| Company | `company` | Link | Company | Yes |
| Approval scope | `approval_scope` | Select | All CARD approvals · Monthly Cards · Transports · Diesel Fills | Yes |


**Delegation window**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| From date | `from_date` | Date |  | Yes |
| To date | `to_date` | Date |  | Yes |
| Delegation status <small>(read only)</small> | `status` | Select | Active · Expired · Cancelled |  |


**Reason**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Reason | `reason` | Small Text |  | Yes |


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, submit, cancel, amend, report, export, print |
