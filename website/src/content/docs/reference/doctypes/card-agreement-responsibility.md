---
title: "Card Agreement Responsibility"
description: "Fields, layout and permissions of the Card Agreement Responsibility DocType."
editUrl: false
sidebar:
  label: "Card Agreement Responsibility"
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
| Cost category | `cost_category` | Select | Rental · Diesel · Transport · Maintenance | Yes |
| Paid by | `paid_by` | Select | Company · Customer · Supplier · Other party | Yes |
| Paying customer | `customer` | Link | Customer |  |
| Paying supplier | `supplier` | Link | Supplier |  |
| Other paying party | `other_party` | Data |  |  |
| Share % | `split_percent` | Percent |  | Yes |
| Only for equipment | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |


## Permissions

No own permissions: access follows the parent document.
