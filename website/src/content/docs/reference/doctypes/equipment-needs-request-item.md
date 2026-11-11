---
title: "Equipment Needs Request Item"
description: "Fields, layout and permissions of the Equipment Needs Request Item DocType."
editUrl: false
sidebar:
  label: "Equipment Needs Request Item"
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
| Kind | `kind` | Select | Part · Tool | Yes |
| Needed item | `item_code` | Link | Item |  |
| Description | `description` | Data |  |  |
| Quantity | `qty` | Float |  | Yes |
| UOM | `uom` | Link | UOM |  |
| Reason | `reason` | Data |  |  |
| Fit for machine <small>(read only)</small> | `fit_status` | Select | Confirmed for machine · Confirmed for model · Not compatible · Pending review · No fitment record |  |
| Reason for an item without a confirmed fit | `fit_reason` | Small Text |  |  |
| Asked recently <small>(read only)</small> | `repeat_flag` | Check |  |  |
| Last asked on <small>(read only)</small> | `last_requested_on` | Date |  |  |


## Permissions

No own permissions: access follows the parent document.
