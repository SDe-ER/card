---
title: "Card Daily Log Settings"
description: "Fields, layout and permissions of the Card Daily Log Settings DocType."
editUrl: false
sidebar:
  label: "Card Daily Log Settings"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/card-daily-log-settings` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Daily log self-approval rule | `self_approval_rule` | Select | Warn only (daily log) · Refuse (daily log) | Yes |
| Daily log supervisor verification required | `require_supervisor_verification` | Check |  |  |


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, report, export |
| Card Manager | read, report |
