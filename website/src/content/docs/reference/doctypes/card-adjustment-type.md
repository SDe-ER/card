---
title: "Card Adjustment Type"
description: "Fields, layout and permissions of the Card Adjustment Type DocType."
editUrl: false
sidebar:
  label: "Card Adjustment Type"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Child table (rows inside another document) |
| Module | Card |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Type name | `type_name` | Data |  | Yes |
| Kind | `kind` | Select | إضافة · خصم | Yes |
| Account | `account` | Link | Account | Yes |
| Taxable | `taxable` | Check |  |  |
| Item <small>(read only)</small> | `item` | Link | Item |  |
| Downtime charge | `is_downtime_charge` | Check |  |  |
| Disabled | `disabled` | Check |  |  |


## Permissions

No own permissions: access follows the parent document.
