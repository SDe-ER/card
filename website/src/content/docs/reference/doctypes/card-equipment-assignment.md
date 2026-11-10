---
title: "Card Equipment Assignment"
description: "Fields, layout and permissions of the Card Equipment Assignment DocType."
editUrl: false
sidebar:
  label: "Card Equipment Assignment"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/card-equipment-assignment` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Equipment | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) | Yes |
| Project | `project` | Link | Project | Yes |
| From date | `from_date` | Date |  |  |
| To date | `to_date` | Date |  |  |
| Equipment name <small>(read only)</small> | `equipment_name` | Data |  |  |
| Cost center | `cost_center` | Link | Cost Center |  |
| Location | `site_location` | Data |  |  |
| Status | `status` | Select | نشط · منتهي |  |

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Notes | `notes` | Small Text |  |  |


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, report, export, print, email |
| Card Manager | read, write, create, report, export, print, email |
| Card User | read, report, print, email |
| Accounts Manager | read, report, export, print |
