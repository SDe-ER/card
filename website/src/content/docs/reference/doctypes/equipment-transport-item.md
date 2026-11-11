---
title: "Equipment Transport Item"
description: "Fields, layout and permissions of the Equipment Transport Item DocType."
editUrl: false
sidebar:
  label: "Equipment Transport Item"
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
| Equipment | `card_equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) | Yes |
| Equipment name <small>(read only)</small> | `equipment_name` | Data |  |  |
| Cost share | `amount` | Currency |  |  |
| Manual share <small>(hidden)</small> | `manual_share` | Check |  |  |
| Previous assignment <small>(read only)</small> | `previous_assignment` | Link | [Card Equipment Assignment](/card/reference/doctypes/card-equipment-assignment/) |  |
| Created assignment <small>(read only)</small> | `created_assignment` | Link | [Card Equipment Assignment](/card/reference/doctypes/card-equipment-assignment/) |  |
| Movement <small>(read only)</small> | `movement` | Select | First entry · Transfer · To workshop · To storage · Return to supplier |  |
| From project <small>(read only)</small> | `from_project` | Link | Project |  |
| Current place <small>(read only)</small> | `from_type` | Select | Project · Workshop · Storage · Supplier |  |
| From place <small>(read only)</small> | `from_location` | Link | Location |  |


## Permissions

No own permissions: access follows the parent document.
