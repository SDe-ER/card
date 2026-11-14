---
title: "Project Diesel Fill"
description: "Fields, layout and permissions of the Project Diesel Fill DocType."
editUrl: false
sidebar:
  label: "Project Diesel Fill"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/project-diesel-fill` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Date | `date` | Date |  | Yes |
| Project | `project` | Link | Project | Yes |
| Supplier | `supplier` | Link | Supplier | Yes |
| Company | `company` | Link | Company | Yes |


**Meter readings**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Opening meter photo | `opening_photo` | Attach Image |  |  |
| Opening reading | `opening_reading` | Float |  |  |
| Closing meter photo | `closing_photo` | Attach Image |  |  |
| Closing reading | `closing_reading` | Float |  |  |
| Litres | `litres` | Float |  | Yes |


**Equipment filled**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Equipment filled | `equipment_filled` | Table | [Diesel Fill Equipment](/card/reference/doctypes/diesel-fill-equipment/) |  |
| Equipment (direct charge) | `card_equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |


**Allocation (estimated, display only)**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Diesel fill allocation <small>(read only)</small> | `diesel_fill_allocation` | Table | [Diesel Fill Allocation](/card/reference/doctypes/diesel-fill-allocation/) |  |
| Allocation review <small>(read only)</small> | `allocation_review` | Small Text |  |  |

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Unit price <small>(read only)</small> | `unit_price` | Currency |  |  |
| Fill amount <small>(read only)</small> | `amount` | Currency |  |  |
| Price source <small>(read only)</small> | `price_source` | Select | Company Price · Exception · Needs Review |  |
| Company price <small>(hidden, read only)</small> | `company_price` | Currency |  |  |
| Diesel price currency <small>(read only)</small> | `price_currency` | Link | Currency |  |
| Diesel price unit of measure <small>(read only)</small> | `price_uom` | Link | UOM |  |
| Diesel price valid from <small>(read only)</small> | `price_valid_from` | Date |  |  |


**Evidence check**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Totalizer check <small>(read only)</small> | `totalizer_check` | Select | Not Checkable · Consistent · Inconsistent |  |
| Evidence warnings <small>(read only)</small> | `evidence_warnings` | Small Text |  |  |


**Operations review**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Review status | `review_status` | Select | Draft · Needs Review · Operations Approved · Rejected |  |
| Review notes | `review_notes` | Small Text |  |  |
| Reviewed by <small>(read only)</small> | `ops_reviewed_by` | Link | User |  |
| Reviewed on <small>(read only)</small> | `ops_reviewed_on` | Datetime |  |  |


**Meter details**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Opening totalizer | `opening_totalizer` | Data |  |  |
| Opening photo time | `opening_photo_time` | Datetime |  |  |
| Closing totalizer | `closing_totalizer` | Data |  |  |
| Closing photo time | `closing_photo_time` | Datetime |  |  |
| Photo location | `photo_location` | Data |  |  |


**Price exception**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Price exception | `price_exception` | Check |  |  |
| Exception reason | `exception_reason` | Small Text |  |  |
| Exception by <small>(read only)</small> | `exception_by` | Link | User |  |
| Exception on <small>(read only)</small> | `exception_on` | Datetime |  |  |


**Supplier invoice and source**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Source key <small>(read only)</small> | `source_key` | Data |  |  |
| Source messages <small>(read only)</small> | `source_messages` | Small Text |  |  |
| Source caption <small>(read only)</small> | `source_caption` | Small Text |  |  |
| Supplier invoice no. <small>(read only)</small> | `supplier_invoice_no` | Data |  |  |
| Invoiced litres <small>(read only)</small> | `invoiced_litres` | Float |  |  |
| Invoice price per litre <small>(read only)</small> | `invoice_unit_price` | Currency |  |  |
| Delivery charge billed as litres <small>(read only)</small> | `delivery_charge_litres` | Float |  |  |
| Invoice evidence <small>(read only)</small> | `invoice_evidence` | Small Text |  |  |


**Cost Center and posting**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Cost Center | `cost_center` | Link | Cost Center |  |
| Purchase Invoice <small>(read only)</small> | `purchase_invoice` | Link | Purchase Invoice |  |
| GL posting <small>(read only)</small> | `gl_posting` | Link | [GL Posting Log](/card/reference/doctypes/gl-posting-log/) |  |
| Posted <small>(read only)</small> | `posted` | Check |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Project Diesel Fill](/card/reference/doctypes/project-diesel-fill/) |  |
| Cancel Reason <small>(read only)</small> | `cancel_reason` | Small Text |  |  |

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Remarks | `remarks` | Small Text |  |  |


**Approval workflow**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Workflow State <small>(hidden, read only)</small> | `workflow_state` | Link | Workflow State |  |
| Return for correction reason <small>(read only)</small> | `return_reason` | Small Text |  |  |


## Child tables

- [Diesel Fill Equipment](/card/reference/doctypes/diesel-fill-equipment/)
- [Diesel Fill Allocation](/card/reference/doctypes/diesel-fill-allocation/)


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
