---
title: "Card Rate Agreement"
description: "Fields, layout and permissions of the Card Rate Agreement DocType."
editUrl: false
sidebar:
  label: "Card Rate Agreement"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/card-rate-agreement` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Agreement valid from | `valid_from` | Date |  | Yes |
| Agreement valid to | `valid_to` | Date |  |  |
| Supplier | `supplier` | Link | Supplier |  |
| Customer | `customer` | Link | Customer |  |


**Agreement applies to**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Equipment | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |
| Equipment type | `equipment_type` | Link | [Card Equipment Type](/card/reference/doctypes/card-equipment-type/) |  |
| Project | `project` | Link | Project |  |
| Work zone | `zone` | Data |  |  |


**Agreement rates**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Currency <small>(read only)</small> | `currency` | Link | Currency | Yes |
| Rate per hour | `hourly_rate` | Currency | currency |  |
| Rate per day | `daily_rate` | Currency | currency |  |
| Rate per month | `monthly_rate` | Currency | currency |  |
| Rate per quantity unit | `quantity_rate` | Currency | currency |  |
| Quantity unit | `quantity_uom` | Link | UOM |  |


**Cost responsibility**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Cost responsibility | `responsibilities` | Table | [Card Agreement Responsibility](/card/reference/doctypes/card-agreement-responsibility/) |  |

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Remarks | `remarks` | Small Text |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Card Rate Agreement](/card/reference/doctypes/card-rate-agreement/) |  |


## Child tables

- [Card Agreement Responsibility](/card/reference/doctypes/card-agreement-responsibility/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, submit, cancel, amend, report, export, print, email |
| Accounts Manager | read, report, export, print |
| Card User | read, report, print |
