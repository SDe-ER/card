---
title: "Diesel Fill Allocation"
description: "Fields, layout and permissions of the Diesel Fill Allocation DocType."
editUrl: false
sidebar:
  label: "Diesel Fill Allocation"
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
| Equipment <small>(read only)</small> | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) | Yes |
| Equipment name <small>(read only)</small> | `card_equipment_name` | Data |  |  |
| Basis <small>(read only)</small> | `basis` | Select | estimated · measured |  |
| Rule <small>(read only)</small> | `rule` | Data |  |  |
| Operating hours <small>(read only)</small> | `hours` | Float |  |  |
| Rate used (L/h) <small>(read only)</small> | `rate_used` | Float |  |  |
| Allocated litres <small>(read only)</small> | `allocated_litres` | Float |  |  |
| Remainder row <small>(read only)</small> | `remainder` | Check |  |  |
| Needs review <small>(read only)</small> | `review_flag` | Check |  |  |
| Frozen on <small>(read only)</small> | `frozen_on` | Datetime |  |  |


## Permissions

No own permissions: access follows the parent document.
