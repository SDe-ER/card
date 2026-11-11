---
title: "Card Diesel Price"
description: "Fields, layout and permissions of the Card Diesel Price DocType."
editUrl: false
sidebar:
  label: "Card Diesel Price"
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
| Diesel price fuel type | `fuel_type` | Select | Diesel |  |
| Diesel price valid from | `valid_from` | Date |  | Yes |
| Diesel unit price (per litre) | `unit_price` | Currency | currency | Yes |
| Diesel price currency | `currency` | Link | Currency |  |
| Diesel price unit of measure | `uom` | Link | UOM |  |


## Permissions

No own permissions: access follows the parent document.
