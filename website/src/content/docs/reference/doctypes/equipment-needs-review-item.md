---
title: "Equipment Needs Review Item"
description: "Fields, layout and permissions of the Equipment Needs Review Item DocType."
editUrl: false
sidebar:
  label: "Equipment Needs Review Item"
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
| Request <small>(read only)</small> | `request` | Link | [Equipment Needs Request](/card/reference/doctypes/equipment-needs-request/) |  |
| Request row <small>(hidden, read only)</small> | `request_item` | Data |  |  |
| Equipment <small>(read only)</small> | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |
| Operator <small>(read only)</small> | `operator` | Link | Employee |  |
| Kind <small>(read only)</small> | `kind` | Select | Part · Tool |  |
| Needed item | `item_code` | Link | Item |  |
| Description <small>(read only)</small> | `description` | Data |  |  |
| UOM | `uom` | Link | UOM |  |
| Requested qty <small>(read only)</small> | `requested_qty` | Float |  |  |
| Found on site | `found_qty` | Float |  |  |
| Approved qty | `approved_qty` | Float |  |  |
| Site inspection | `inspection` | Select | Not inspected · Inspected |  |
| Inspection note | `inspection_note` | Data |  |  |
| Inspected by <small>(read only)</small> | `inspected_by` | Link | User |  |
| Inspected on <small>(read only)</small> | `inspected_on` | Date |  |  |
| Supply route | `route` | Select | From store · Buy for project |  |
| Warehouse | `warehouse` | Link | Warehouse |  |
| In stock <small>(read only)</small> | `stock_qty` | Float |  |  |
| Asked recently <small>(read only)</small> | `repeat_flag` | Check |  |  |
| Fit for machine <small>(read only)</small> | `fit_status` | Select | Confirmed for machine · Confirmed for model · Not compatible · Pending review · No fitment record |  |
| Reason for an item without a confirmed fit <small>(read only)</small> | `fit_reason` | Small Text |  |  |
| Material Request <small>(read only)</small> | `material_request` | Link | Material Request |  |
| Tool custody <small>(read only)</small> | `tool_custody` | Link | [Employee Tool Custody](/card/reference/doctypes/employee-tool-custody/) |  |
| Handed over qty <small>(read only)</small> | `handed_qty` | Float |  |  |


## Permissions

No own permissions: access follows the parent document.
