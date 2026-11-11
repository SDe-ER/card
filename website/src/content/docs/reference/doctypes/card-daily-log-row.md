---
title: "Card Daily Log Row"
description: "Fields, layout and permissions of the Card Daily Log Row DocType."
editUrl: false
sidebar:
  label: "Card Daily Log Row"
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
| Equipment | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) | Yes |
| Equipment name <small>(read only)</small> | `equipment_name` | Data |  |  |
| Day shift hours | `day_hours` | Float |  |  |
| Night shift hours | `night_hours` | Float |  |  |
| Stop reason | `stop_reason` | Link | [Card Stop Reason](/card/reference/doctypes/card-stop-reason/) |  |
| Stopped hours | `stopped_hours` | Float |  |  |
| Responsible party | `responsible_party_type` | Select | Company · Supplier · Customer · Other |  |
| Responsible party record | `responsible_party` | Dynamic Link | responsible_party_type |  |
| Responsible party name | `responsible_party_name` | Data |  |  |
| Notes | `notes` | Small Text |  |  |


## Permissions

No own permissions: access follows the parent document.
