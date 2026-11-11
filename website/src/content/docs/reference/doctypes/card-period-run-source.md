---
title: "Card Period Run Source"
description: "Fields, layout and permissions of the Card Period Run Source DocType."
editUrl: false
sidebar:
  label: "Card Period Run Source"
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
| Period run source type <small>(read only)</small> | `source_doctype` | Select | Card Monthly Card · Project Diesel Fill · Equipment Transport |  |
| Period run source document <small>(read only)</small> | `source_name` | Data |  |  |
| Equipment <small>(read only)</small> | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |
| Project <small>(read only)</small> | `project` | Link | Project |  |
| Supplier <small>(read only)</small> | `supplier` | Link | Supplier |  |
| Customer <small>(read only)</small> | `customer` | Link | Customer |  |
| Billed on the supplier side <small>(read only)</small> | `supplier_side` | Check |  |  |
| Billed on the customer side <small>(read only)</small> | `customer_side` | Check |  |  |
| Period run supplier gross source amount <small>(read only)</small> | `supplier_amount` | Currency | currency |  |
| Period run customer gross source amount <small>(read only)</small> | `customer_amount` | Currency | currency |  |
| Fill supplier VAT-registered <small>(read only)</small> | `supplier_vat_registered` | Check |  |  |
| Supplier side already posted <small>(read only)</small> | `supplier_posted` | Check |  |  |
| Customer side already posted <small>(read only)</small> | `customer_posted` | Check |  |  |
| Period run currency <small>(hidden, read only)</small> | `currency` | Link | Currency |  |
| Source document last modified <small>(read only)</small> | `source_modified` | Datetime |  |  |
| Source document fingerprint <small>(read only)</small> | `content_hash` | Data |  |  |


## Permissions

No own permissions: access follows the parent document.
