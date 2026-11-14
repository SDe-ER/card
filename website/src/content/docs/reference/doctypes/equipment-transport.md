---
title: "Equipment Transport"
description: "Fields, layout and permissions of the Equipment Transport DocType."
editUrl: false
sidebar:
  label: "Equipment Transport"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/equipment-transport` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Date | `date` | Date |  | Yes |
| To project | `project` | Link | Project |  |
| Transport supplier | `transport_supplier` | Link | Supplier |  |
| Company | `company` | Link | Company | Yes |
| Equipment <small>(hidden, read only)</small> | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |
| From (old text) <small>(hidden, read only)</small> | `from_location` | Data |  |  |
| To (old text) <small>(hidden, read only)</small> | `to_location` | Data |  |  |
| Transporter cost | `amount` | Currency |  |  |
| Cost Center <small>(read only)</small> | `cost_center` | Link | Cost Center |  |

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Equipment | `items` | Table | [Equipment Transport Item](/card/reference/doctypes/equipment-transport-item/) |  |


**Linked Records**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Purchase Invoice <small>(read only)</small> | `purchase_invoice` | Link | Purchase Invoice |  |
| Remarks | `remarks` | Small Text |  |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Equipment Transport](/card/reference/doctypes/equipment-transport/) |  |
| Cancel Reason <small>(read only)</small> | `cancel_reason` | Small Text |  |  |
| GL posting <small>(read only)</small> | `gl_posting` | Link | [GL Posting Log](/card/reference/doctypes/gl-posting-log/) |  |
| Posted <small>(read only)</small> | `posted` | Check |  |  |
| Transport method | `transport_method` | Select | Truck Head · Winch · Low-bed · Self-driven · Other |  |
| Previous assignment <small>(read only)</small> | `previous_assignment` | Link | [Card Equipment Assignment](/card/reference/doctypes/card-equipment-assignment/) |  |
| Created assignment <small>(read only)</small> | `created_assignment` | Link | [Card Equipment Assignment](/card/reference/doctypes/card-equipment-assignment/) |  |
| Equipment ownership | `ownership` | Select | ملك · إيجار · طرف ثالث |  |
| Equipment supplier | `equipment_supplier` | Link | Supplier |  |
| Transport cost borne by <small>(read only)</small> | `cost_borne_by` | Select | Company · Equipment Supplier · Customer |  |
| Destination | `destination_type` | Select | Project · Workshop · Storage · Supplier | Yes |
| To place | `destination_location` | Link | Location |  |
| From <small>(read only)</small> | `source_type` | Select | Project · Workshop · Storage · Supplier |  |
| From project <small>(read only)</small> | `source_project` | Link | Project |  |
| From place <small>(read only)</small> | `source_location` | Link | Location |  |


**Route**


**Cost and date**


**Cost responsibility**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Transport responsibility | `responsibility` | Select | Company bears the cost · Company pays, bills the customer · Company pays, recovers from equipment supplier · Equipment supplier bears the cost · Customer pays the transporter directly · Other party bears the cost · No transport charge · Responsibility needs review | Yes |
| Transporter paid by <small>(hidden, read only)</small> | `payer` | Select | Company · Equipment Supplier · Customer · Other Party · No charge |  |
| Cost borne by <small>(hidden, read only)</small> | `cost_bearer` | Select | Company · Equipment Supplier · Customer · Other Party |  |
| Cost charged to <small>(hidden, read only)</small> | `cost_basis` | Select | Project · Workshop or storage · Company overhead |  |
| Customer billing eligible <small>(hidden, read only)</small> | `customer_billable` | Check |  |  |
| Supplier recovery eligible <small>(hidden, read only)</small> | `supplier_recoverable` | Check |  |  |
| Cost project | `cost_project` | Link | Project |  |
| Overhead cost center <small>(hidden)</small> | `overhead_cost_center` | Link | Cost Center |  |


**Financial decision**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Financial status <small>(read only)</small> | `financial_status` | Select | No decision needed · Pending · Approved · Rejected |  |
| Cost decision <small>(read only)</small> | `financial_decision` | Select | Bill customer · Company absorbs · Recover from equipment supplier · Return for correction |  |
| Customer <small>(read only)</small> | `customer` | Link | Customer |  |
| Billing project <small>(read only)</small> | `billing_project` | Link | Project |  |
| Agreed billing amount (before VAT) <small>(read only)</small> | `billing_amount` | Currency |  |  |
| Billing <small>(read only)</small> | `billing_mode` | Select | Monthly invoice · Separate invoice |  |
| Authorization reference <small>(read only)</small> | `billing_reference` | Data |  |  |
| Authorization document <small>(read only)</small> | `billing_document` | Attach |  |  |
| Absorption reason <small>(read only)</small> | `absorption_reason` | Small Text |  |  |
| Recovery method <small>(read only)</small> | `recovery_mode` | Select | Deduct from monthly dues · Adjustment document |  |
| Recovery amount <small>(read only)</small> | `recovery_amount` | Currency |  |  |
| Decision note <small>(read only)</small> | `decision_note` | Small Text |  |  |
| Decided by <small>(read only)</small> | `financial_approver` | Link | User |  |
| Decided on <small>(read only)</small> | `financial_decided_on` | Datetime |  |  |
| Transport submitted by <small>(read only)</small> | `submitted_by` | Link | User |  |
| Transport edited by <small>(hidden, read only)</small> | `edited_by` | Small Text |  |  |
| Move-day rule <small>(read only)</small> | `move_day_rule` | Select | New assignment starts the day after the move · New assignment starts on the move day |  |
| Other party type | `party_type` | Select | Supplier · Customer · Employee |  |
| Other party bearing the transport cost | `party` | Dynamic Link | party_type |  |
| Agreed amount (not company cost) | `informational_amount` | Currency |  |  |


**Intake source**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Intake channel | `intake_channel` | Select | Manual · Paper · WhatsApp · Email · Other |  |
| Intake source key | `intake_source_key` | Data |  |  |
| Intake received on | `intake_received_on` | Datetime |  |  |
| Intake evidence | `intake_evidence` | Attach |  |  |
| Intake evidence SHA-256 <small>(read only)</small> | `intake_evidence_hash` | Data |  |  |


**Approval workflow**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Workflow State <small>(hidden, read only)</small> | `workflow_state` | Link | Workflow State |  |
| Return for correction reason <small>(read only)</small> | `return_reason` | Small Text |  |  |


## Child tables

- [Equipment Transport Item](/card/reference/doctypes/equipment-transport-item/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, submit, cancel, amend, report, export, print, email |
| Card User | read, write, create, report, print, email |
| Accounts Manager | read, report, export, print |
| System Manager (permlevel 1) | read |
| Card Manager (permlevel 1) | read |
| Accounts Manager (permlevel 1) | read |
