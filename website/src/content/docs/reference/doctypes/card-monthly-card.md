---
title: "Card Monthly Card"
description: "Fields, layout and permissions of the Card Monthly Card DocType."
editUrl: false
sidebar:
  label: "Card Monthly Card"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/card-monthly-card` |


## Fields


**Card details**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Equipment | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) | Yes |
| Project | `project` | Link | Project | Yes |
| Company <small>(read only)</small> | `company` | Link | Company | Yes |
| Project name <small>(hidden, read only)</small> | `project_name` | Data |  |  |
| Location | `site_location` | Data |  |  |
| Driver / Operator | `operator_name` | Data |  |  |
| Shift type | `shift` | Select | نهاري · ليلي | Yes |
| Month | `month` | Select | 01 · 02 · 03 · 04 · 05 · 06 · 07 · 08 · 09 · 10 · 11 · 12 | Yes |
| Year | `year` | Int |  | Yes |
| Image <small>(hidden)</small> | `image` | Attach Image |  |  |
| Equipment name <small>(read only)</small> | `equipment_name` | Data |  |  |
| Ownership <small>(read only)</small> | `ownership` | Data |  |  |
| Owner <small>(read only)</small> | `supplier` | Link | Supplier |  |
| From date <small>(read only)</small> | `from_date` | Date |  |  |
| To date <small>(read only)</small> | `to_date` | Date |  |  |


**Days of month**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Days | `days` | Table | [Card Monthly Card Day](/card/reference/doctypes/card-monthly-card-day/) | Yes |


**Totals**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Rate type <small>(read only)</small> | `rate_type` | Data |  |  |
| Rate <small>(read only)</small> | `rate` | Currency |  |  |
| Working days <small>(read only)</small> | `working_days` | Int |  |  |
| Total operating hours <small>(read only)</small> | `total_working_hours` | Float |  |  |
| Billable stopped hours <small>(read only)</small> | `billable_stopped_hours` | Float |  |  |
| Billable stopped days <small>(read only)</small> | `billable_stopped_days` | Int |  |  |
| Supplier billable stopped hours <small>(read only)</small> | `supplier_billable_stopped_hours` | Float |  |  |
| Customer billable stopped hours <small>(read only)</small> | `customer_billable_stopped_hours` | Float |  |  |
| Total amount <small>(read only)</small> | `amount` | Currency |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) |  |
| Cancel Reason <small>(read only)</small> | `cancel_reason` | Small Text |  |  |


**Additions and deductions**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Additions and deductions | `adjustments` | Table | [Card Monthly Card Adjustment](/card/reference/doctypes/card-monthly-card-adjustment/) |  |
| Total additions <small>(read only)</small> | `total_additions` | Currency |  |  |
| Total deductions <small>(read only)</small> | `total_deductions` | Currency |  |  |
| Net due <small>(read only)</small> | `net_amount` | Currency |  |  |


**Monthly card approval**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Approval tier <small>(read only)</small> | `approval_tier` | Int |  |  |
| Approval tier name <small>(read only)</small> | `approval_tier_name` | Data |  |  |
| Monthly card submitted by <small>(read only)</small> | `submitted_by` | Link | User |  |
| Monthly card approved by <small>(read only)</small> | `approved_by` | Link | User |  |
| Monthly card approved on <small>(read only)</small> | `approved_on` | Datetime |  |  |
| Monthly card approved by its own preparer <small>(read only)</small> | `self_approved` | Check |  |  |
| Monthly card edited by <small>(hidden, read only)</small> | `edited_by` | Small Text |  |  |


**Accounting**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| GL posting <small>(read only)</small> | `gl_posting` | Link | [GL Posting Log](/card/reference/doctypes/gl-posting-log/) |  |
| Posted <small>(read only)</small> | `posted` | Check |  |  |
| Purchase Invoice <small>(read only)</small> | `purchase_invoice` | Link | Purchase Invoice |  |
| Daily hours (used) <small>(read only)</small> | `daily_hours_used` | Float |  |  |
| Hourly rate (used) <small>(read only)</small> | `hourly_rate_used` | Currency |  |  |
| Fuel charged to (used) <small>(read only)</small> | `diesel_policy_used` | Data |  |  |
| Card direction <small>(read only)</small> | `card_direction` | Select | مستأجَرة من مورد · مؤجَّرة لعميل · إيجار من الباطن · تشغيل داخلي |  |
| Customer <small>(read only)</small> | `customer` | Link | Customer |  |
| Customer rate type <small>(read only)</small> | `customer_rate_type` | Select | باليوم · بالساعة · بالشهر · بالمتر المكعب |  |
| Customer rate <small>(read only)</small> | `customer_rate` | Currency |  |  |
| Day billing basis <small>(read only)</small> | `day_billing_basis` | Select | Prorated by hours · Full day |  |
| Customer amount <small>(read only)</small> | `customer_amount` | Currency |  |  |
| Customer hourly rate used <small>(read only)</small> | `customer_rate_used` | Currency |  |  |
| Load volume used (m³) <small>(read only)</small> | `load_volume_used` | Float |  |  |
| Total loads <small>(read only)</small> | `total_loads` | Int |  |  |
| Total volume (m³) <small>(read only)</small> | `total_volume_m3` | Float |  |  |
| Direction used <small>(read only)</small> | `direction_used` | Data |  |  |
| Customer used <small>(read only)</small> | `customer_used` | Data |  |  |
| Rate basis used <small>(read only)</small> | `rate_basis_used` | Data |  |  |
| Day billing basis used <small>(read only)</small> | `day_billing_basis_used` | Select | Prorated by hours · Full day |  |


**Equipment information**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Customer net amount <small>(read only)</small> | `customer_net_amount` | Currency |  |  |
| Sales Invoice <small>(read only)</small> | `sales_invoice` | Link | Sales Invoice |  |
| Operator provided by <small>(hidden, read only)</small> | `operator_on` | Data |  |  |
| Operator | `operator` | Link | Employee |  |


**Approval workflow**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Workflow State <small>(hidden, read only)</small> | `workflow_state` | Link | Workflow State |  |
| Return for correction reason <small>(read only)</small> | `return_reason` | Small Text |  |  |


## Child tables

- [Card Monthly Card Day](/card/reference/doctypes/card-monthly-card-day/)
- [Card Monthly Card Adjustment](/card/reference/doctypes/card-monthly-card-adjustment/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, submit, cancel, amend, report, export, print, email |
| Card User | read, write, create, report, print, email |
| Accounts Manager | read, report, export, print |
| System Manager (permlevel 1) | read, write |
| Card Manager (permlevel 1) | read, write |
| Card User (permlevel 1) | read |
| Accounts Manager (permlevel 1) | read |
