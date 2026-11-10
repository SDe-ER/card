---
title: "Card Equipment Type"
description: "Fields, layout and permissions of the Card Equipment Type DocType."
editUrl: false
sidebar:
  label: "Card Equipment Type"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/card-equipment-type` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Type name | `equipment_type_name` | Data |  | Yes |
| Description | `description` | Small Text |  |  |
| Equipment category | `equipment_category` | Link | [Card Equipment Category](/card/reference/doctypes/card-equipment-category/) | Yes |
| Meter type | `meter_type` | Select | ساعات · كيلومترات · بدون عداد |  |
| Asset category | `asset_category` | Link | Asset Category |  |


**Default consumption rates**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Type default consumption rates (litres per hour) | `default_consumption_rates` | Table | [Card Type Consumption Rate](/card/reference/doctypes/card-type-consumption-rate/) |  |


## Child tables

- [Card Type Consumption Rate](/card/reference/doctypes/card-type-consumption-rate/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, report, export, print, email |
| Card Manager | read, write, create, report, export, print, email |
| Card User | read, write, create, report, print, email |
| Accounts Manager | read, report, export, print |
