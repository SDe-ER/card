---
title: "Card Settings"
description: "Fields, layout and permissions of the Card Settings DocType."
editUrl: false
sidebar:
  label: "Card Settings"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Single (one settings record) |
| Module | Card |
| Open in Desk | `/app/card-settings` |


## Fields


### Accounting


**Policy**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Enable accounting posting | `enable_accounting` | Check |  |  |
| Auto-submit postings <small>(hidden, read only)</small> | `auto_submit` | Check |  |  |


**Company Configuration**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company settings | `company_settings` | Table | [Card Company Settings](/card/reference/doctypes/card-company-settings/) |  |


### Operations


**Defaults**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Default shift | `default_shift` | Select | نهاري · ليلي |  |
| Max day-shift hours | `max_day_shift_hours` | Float |  |  |
| Max night-shift hours | `max_night_shift_hours` | Float |  |  |
| Default daily hours (new equipment only) | `default_daily_hours` | Float |  |  |
| Default fuel charged to (new equipment) | `default_fuel_charged_to` | Select | المؤجر · الشركة |  |
| Default operator charged to (new equipment) | `default_operator_on` | Select | المؤجر · الشركة |  |
| Reconciliation tolerance | `reconciliation_tolerance` | Currency |  |  |


**Warnings**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Warn when day hours exceed daily hours | `warn_on_shift_hours_exceeded` | Check |  |  |
| Warn when card dates fall outside rental period | `warn_outside_rental_period` | Check |  |  |


**Report defaults**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Default statement type | `default_statement_type` | Select | مورد · معدات ملك |  |
| Include draft cards in reports | `include_draft_in_reports` | Check |  |  |


### Period Lock


**Period lock**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Period lock date | `period_lock_date` | Date |  |  |
| Period lock override role | `period_lock_override_role` | Link | Role |  |


### Notifications


**Notifications (all off by default)**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Notify on card submit | `notify_on_card_submit` | Check |  |  |
| Notify on accounting posting <small>(hidden, read only)</small> | `notify_on_posting` | Check |  |  |
| Notify on period lock override | `notify_on_period_lock_override` | Check |  |  |
| Default rate basis | `default_rate_basis` | Select | باليوم · بالساعة · بالشهر |  |
| Standard month hours | `standard_month_hours` | Float |  |  |
| Daily equipment location sync | `sync_equipment_location_daily` | Check |  |  |


### Diesel Settings


**Diesel price schedule**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Diesel price schedule | `diesel_price_schedule` | Table | [Card Diesel Price](/card/reference/doctypes/card-diesel-price/) |  |


**Diesel supplier**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Diesel supplier policy | `diesel_supplier_policy` | Select | ثابت · متغير |  |
| Diesel supplier | `diesel_supplier` | Link | Supplier |  |
| Diesel supplier editor role | `diesel_supplier_editor_role` | Link | Role |  |
| Diesel price exception role | `diesel_price_exception_role` | Link | Role |  |
| Diesel zero price role | `diesel_zero_price_role` | Link | Role |  |


### Transport Settings


**Transport prices**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Transport price editor role | `transport_price_editor_role` | Link | Role |  |
| Transport price per project | `project_transport_prices` | Table | [Card Project Transport Price](/card/reference/doctypes/card-project-transport-price/) |  |


### Warehouse & Cost Centers


**Addition/Deduction Types**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Addition/Deduction Types | `adjustment_types` | Table | [Card Adjustment Type](/card/reference/doctypes/card-adjustment-type/) |  |
| Cost center per workshop / storage place | `location_cost_centers` | Table | [Card Location Cost Center](/card/reference/doctypes/card-location-cost-center/) |  |


### Materials


**Equipment needs**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Main store | `default_store_warehouse` | Link | Warehouse |  |
| Tool custody store | `tool_custody_warehouse` | Link | Warehouse |  |
| Flag a repeated request within (days) | `repeat_request_days` | Int |  |  |


### Advanced Permissions


## Child tables

- [Card Company Settings](/card/reference/doctypes/card-company-settings/)
- [Card Diesel Price](/card/reference/doctypes/card-diesel-price/)
- [Card Project Transport Price](/card/reference/doctypes/card-project-transport-price/)
- [Card Adjustment Type](/card/reference/doctypes/card-adjustment-type/)
- [Card Location Cost Center](/card/reference/doctypes/card-location-cost-center/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create |
| System Manager (permlevel 1) | read, write |
| System Manager (permlevel 2) | read, write |
| Accounts Manager | read, write |
| Accounts Manager (permlevel 1) | read, write |
| Accounts Manager (permlevel 2) | read |
| Card Manager | read |
| Card Manager (permlevel 2) | read |
