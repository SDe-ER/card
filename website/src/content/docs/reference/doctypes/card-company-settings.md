---
title: "Card Company Settings"
description: "Fields, layout and permissions of the Card Company Settings DocType."
editUrl: false
sidebar:
  label: "Card Company Settings"
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


**Accounts**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Equipment rental expense account | `equipment_rental_expense_account` | Link | Account |  |
| Diesel expense account | `diesel_expense_account` | Link | Account |  |
| Transport/mobilization expense account | `transport_expense_account` | Link | Account |  |
| Equipment rental income account | `equipment_rental_income_account` | Link | Account |  |
| Payable (Creditors) | `payable_account` | Link | Account |  |
| Receivable (Debtors) | `receivable_account` | Link | Account |  |
| Cost center | `cost_center` | Link | Cost Center |  |


**Tax templates**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Purchase tax template | `purchase_tax_template` | Link | Purchase Taxes and Charges Template |  |
| Sales tax template | `sales_tax_template` | Link | Sales Taxes and Charges Template |  |


**Items**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Rental item | `rental_item` | Link | Item |  |
| Diesel item | `diesel_item` | Link | Item |  |
| Transport item | `transport_item` | Link | Item |  |
| Rental-out item | `rental_out_item` | Link | Item |  |


**Pricing**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Diesel unit price (per litre) | `diesel_unit_price` | Currency |  |  |


**Settlement**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Bank / cash account <small>(hidden, read only)</small> | `bank_cash_account` | Link | Account |  |
| Mode of payment <small>(hidden, read only)</small> | `mode_of_payment` | Link | Mode of Payment |  |
| VAT item tax template (company rate) | `vat_item_tax_template` | Link | Item Tax Template |  |
| VAT 0% item tax template | `vat_zero_item_tax_template` | Link | Item Tax Template |  |
| Diesel price VAT basis | `diesel_price_vat_basis` | Select | Exclusive · Inclusive |  |
| Diesel fill project check | `diesel_fill_project_check` | Select | Off (diesel project check) · Warn only (diesel project check) · Refuse (diesel project check) |  |


**Equipment and transport**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Initial place of new equipment | `initial_location` | Link | Location |  |
| Move-day rule | `move_day_rule` | Select | New assignment starts the day after the move · New assignment starts on the move day |  |
| Equipment status rule | `equipment_status_rule` | Select | Warn only (equipment status) · Refuse (equipment status) |  |
| Monthly card approval rule | `card_approval_rule` | Select | Warn only (card approval) · Refuse (card approval) |  |


**Materials**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Main store | `store_warehouse` | Link | Warehouse |  |
| Tool custody store | `custody_warehouse` | Link | Warehouse |  |
| Flag a repeated request within (days) | `repeat_request_days` | Int |  |  |


**Transport responsibility posting**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Transport responsibility posting | `transport_responsibility_posting` | Select | Hold (transport responsibility posting) · Post (transport responsibility posting) |  |
| Transport recharge income account | `transport_recharge_income_account` | Link | Account |  |


## Permissions

No own permissions: access follows the parent document.
