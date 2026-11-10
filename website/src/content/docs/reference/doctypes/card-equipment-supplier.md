---
title: "Card Equipment Supplier"
description: "Fields, layout and permissions of the Card Equipment Supplier DocType."
editUrl: false
sidebar:
  label: "Card Equipment Supplier"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/card-equipment-supplier` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Supplier | `supplier` | Link | Supplier | Yes |
| Supplier name <small>(read only)</small> | `supplier_name` | Data |  |  |
| First operating month <small>(hidden, read only)</small> | `first_month` | Data |  |  |
| Last operating month <small>(hidden, read only)</small> | `last_month` | Data |  |  |


**Statistics**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Number of equipment <small>(hidden, read only)</small> | `equipment_count` | Int |  |  |
| Number of approved cards <small>(hidden, read only)</small> | `card_count` | Int |  |  |
| Total hours <small>(hidden, read only)</small> | `total_hours` | Float |  |  |
| Total net cards <small>(hidden, read only)</small> | `total_net` | Currency |  |  |
| Last updated <small>(hidden, read only)</small> | `last_refreshed` | Datetime |  |  |


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, report, export, print, email |
| Card Manager | read, write, create, report, export, print, email |
| Card User | read, report, print, email |
| Accounts Manager | read, report, export, print |
