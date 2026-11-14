---
title: "Reports"
description: "Every CARD report with its filters and the roles that can run it."
editUrl: false
sidebar:
  order: 2
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| Reports | Based on | Roles |
|---|---|---|
| [Asset Mapping Review](#asset-mapping-review) | [Card Equipment](/card/reference/doctypes/card-equipment/) | System Manager, Card Manager, Accounts Manager |
| [Card Settlement Status](#card-settlement-status) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Accounts Manager |
| [Diesel Group Analysis](#diesel-group-analysis) | [Equipment Operating Group](/card/reference/doctypes/equipment-operating-group/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Diesel Invoice Reconciliation](#diesel-invoice-reconciliation) | [Project Diesel Fill](/card/reference/doctypes/project-diesel-fill/) | System Manager, Accounts Manager |
| [Diesel Variance Anomaly](#diesel-variance-anomaly) | [Project Diesel Fill](/card/reference/doctypes/project-diesel-fill/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Equipment Consumption](#equipment-consumption) | [Card Equipment](/card/reference/doctypes/card-equipment/) | System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager |
| [Equipment Customer Statement](#equipment-customer-statement) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Equipment Customers Summary](#equipment-customers-summary) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Equipment Diesel Analysis](#equipment-diesel-analysis) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Equipment Diesel Consumption](#equipment-diesel-consumption) | [Project Diesel Fill](/card/reference/doctypes/project-diesel-fill/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Equipment Downtime](#equipment-downtime) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Equipment Expenses Without Equipment](#equipment-expenses-without-equipment) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Accounts Manager |
| [Equipment Location History](#equipment-location-history) | [Card Equipment](/card/reference/doctypes/card-equipment/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Equipment Maintenance Cost](#equipment-maintenance-cost) | Purchase Invoice | System Manager, Accounts Manager |
| [Equipment Make Model Values](#equipment-make-model-values) | [Card Equipment](/card/reference/doctypes/card-equipment/) | System Manager, Card Manager |
| [Equipment Meter Reconciliation](#equipment-meter-reconciliation) | [Card Equipment](/card/reference/doctypes/card-equipment/) | System Manager, Card Manager, Accounts Manager |
| [Equipment Needs Summary](#equipment-needs-summary) | [Equipment Needs Review](/card/reference/doctypes/equipment-needs-review/) | System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager |
| [Equipment Partial Margin](#equipment-partial-margin) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Accounts Manager |
| [Equipment Supplier Statement](#equipment-supplier-statement) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Equipment Suppliers Summary](#equipment-suppliers-summary) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Operating Cost by Project](#operating-cost-by-project) | [Project Diesel Fill](/card/reference/doctypes/project-diesel-fill/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Posting Source Integrity](#posting-source-integrity) | [GL Posting Log](/card/reference/doctypes/gl-posting-log/) | System Manager, Accounts Manager |
| [Repeat Equipment Requests](#repeat-equipment-requests) | [Equipment Needs Request](/card/reference/doctypes/equipment-needs-request/) | System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager |
| [Transport Accounting Review](#transport-accounting-review) | [Equipment Transport](/card/reference/doctypes/equipment-transport/) | System Manager, Accounts Manager |
| [Transport Cost by Project](#transport-cost-by-project) | [Equipment Transport](/card/reference/doctypes/equipment-transport/) | System Manager, Card Manager, Card User, Accounts Manager |
| [Unbilled Card Work](#unbilled-card-work) | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | System Manager, Accounts Manager, Card Manager |
| [Worker Custody](#worker-custody) | [Employee Tool Custody](/card/reference/doctypes/employee-tool-custody/) | System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager |


<h2 id="asset-mapping-review">Asset Mapping Review</h2>

- Type: Script Report
- Based on: Card Equipment
- Roles: System Manager, Card Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| Show | `show` | Select |  |


<h2 id="card-settlement-status">Card Settlement Status</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| Party type | `party_type` | Select | Yes |
| Party | `party` | Dynamic Link |  |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |


<h2 id="diesel-group-analysis">Diesel Group Analysis</h2>

- Type: Script Report
- Based on: Equipment Operating Group
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Operating group | `group` | Link → Equipment Operating Group |  |


<h2 id="diesel-invoice-reconciliation">Diesel Invoice Reconciliation</h2>

- Type: Script Report
- Based on: Project Diesel Fill
- Roles: System Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| Diesel suppliers (one delivery stream) | `suppliers` | MultiSelectList |  |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Diesel sessions to include | `session_status` | Select |  |
| Invoice date window (days) | `date_window_days` | Int |  |
| Delivery charge up to (litres) | `max_delivery_litres` | Float |  |


<h2 id="diesel-variance-anomaly">Diesel Variance Anomaly</h2>

- Type: Script Report
- Based on: Project Diesel Fill
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Project | `project` | Autocomplete |  |
| Equipment | `equipment` | Link → Card Equipment |  |
| Equipment type | `equipment_type` | Link → Card Equipment Type |  |


<h2 id="equipment-consumption">Equipment Consumption</h2>

- Type: Script Report
- Based on: Card Equipment
- Roles: System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| From date | `from_date` | Date |  |
| To date | `to_date` | Date |  |
| Project | `project` | Link → Project |  |
| Equipment | `equipment` | Link → Card Equipment |  |


<h2 id="equipment-customer-statement">Equipment Customer Statement</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| Customer | `customer` | Link → Card Equipment Customer | Yes |
| From month | `from_month` | Select | Yes |
| From year | `from_year` | Int | Yes |
| To month | `to_month` | Select | Yes |
| To year | `to_year` | Int | Yes |
| Project | `project` | Autocomplete |  |
| Equipment | `equipment` | Link → Card Equipment |  |
| Equipment type | `equipment_type` | Link → Card Equipment Type |  |
| Include drafts | `include_draft` | Check |  |


<h2 id="equipment-customers-summary">Equipment Customers Summary</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From month | `from_month` | Select | Yes |
| From year | `from_year` | Int | Yes |
| To month | `to_month` | Select | Yes |
| To year | `to_year` | Int | Yes |
| Project | `project` | Autocomplete |  |


<h2 id="equipment-diesel-analysis">Equipment Diesel Analysis</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From month | `from_month` | Select | Yes |
| From year | `from_year` | Int | Yes |
| To month | `to_month` | Select |  |
| To year | `to_year` | Int |  |
| Project | `project` | Autocomplete |  |
| Equipment | `equipment` | Link → Card Equipment |  |


<h2 id="equipment-diesel-consumption">Equipment Diesel Consumption</h2>

- Type: Script Report
- Based on: Project Diesel Fill
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date |  |
| To date | `to_date` | Date |  |
| Project | `project` | Autocomplete |  |
| Equipment | `equipment` | Link → Card Equipment |  |


<h2 id="equipment-downtime">Equipment Downtime</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Group downtime by | `group_by` | Select |  |
| Project | `project` | Autocomplete |  |
| Equipment | `equipment` | Link → Card Equipment |  |
| Stop reason | `stop_reason` | Link → Card Stop Reason |  |
| Responsible party | `responsible_party_type` | Select |  |
| Include draft cards | `include_drafts` | Check |  |


<h2 id="equipment-expenses-without-equipment">Equipment Expenses Without Equipment</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date |  |
| To date | `to_date` | Date |  |


<h2 id="equipment-location-history">Equipment Location History</h2>

- Type: Script Report
- Based on: Card Equipment
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Equipment | `equipment` | Link → Card Equipment |  |


<h2 id="equipment-maintenance-cost">Equipment Maintenance Cost</h2>

- Type: Script Report
- Based on: Purchase Invoice
- Roles: System Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Project | `project` | Autocomplete |  |
| Equipment | `equipment` | Link → Card Equipment |  |


<h2 id="equipment-make-model-values">Equipment Make Model Values</h2>

- Type: Script Report
- Based on: Card Equipment
- Roles: System Manager, Card Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Without equipment model only | `unlinked_only` | Check |  |


<h2 id="equipment-meter-reconciliation">Equipment Meter Reconciliation</h2>

- Type: Script Report
- Based on: Card Equipment
- Roles: System Manager, Card Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| Equipment | `equipment` | Link → Card Equipment |  |
| View | `view` | Select |  |
| Show | `show` | Select |  |
| Allowed difference % | `tolerance_pct` | Float |  |


<h2 id="equipment-needs-summary">Equipment Needs Summary</h2>

- Type: Script Report
- Based on: Equipment Needs Review
- Roles: System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Project | `project` | Link → Project |  |
| Management approval | `approval_status` | Select |  |


<h2 id="equipment-partial-margin">Equipment Partial Margin</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Project | `project` | Autocomplete |  |
| Equipment | `equipment` | Link → Card Equipment |  |


<h2 id="equipment-supplier-statement">Equipment Supplier Statement</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| Statement type | `statement_type` | Select | Yes |
| Supplier | `supplier` | Link → Card Equipment Supplier | Yes |
| From month | `from_month` | Select | Yes |
| From year | `from_year` | Int | Yes |
| To month | `to_month` | Select | Yes |
| To year | `to_year` | Int | Yes |
| Project | `project` | Autocomplete |  |
| Equipment | `equipment` | Link → Card Equipment |  |
| Equipment type | `equipment_type` | Link → Card Equipment Type |  |
| Include drafts | `include_draft` | Check |  |


<h2 id="equipment-suppliers-summary">Equipment Suppliers Summary</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From month | `from_month` | Select | Yes |
| From year | `from_year` | Int | Yes |
| To month | `to_month` | Select | Yes |
| To year | `to_year` | Int | Yes |
| Project | `project` | Autocomplete |  |


<h2 id="operating-cost-by-project">Operating Cost by Project</h2>

- Type: Script Report
- Based on: Project Diesel Fill
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date |  |
| To date | `to_date` | Date |  |
| Project | `project` | Autocomplete |  |


<h2 id="posting-source-integrity">Posting Source Integrity</h2>

- Type: Script Report
- Based on: GL Posting Log
- Roles: System Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Show | `show` | Select |  |


<h2 id="repeat-equipment-requests">Repeat Equipment Requests</h2>

- Type: Script Report
- Based on: Equipment Needs Request
- Roles: System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Project | `project` | Link → Project |  |
| Equipment | `equipment` | Link → Card Equipment |  |


<h2 id="transport-accounting-review">Transport Accounting Review</h2>

- Type: Script Report
- Based on: Equipment Transport
- Roles: System Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Show | `show` | Select |  |


<h2 id="transport-cost-by-project">Transport Cost by Project</h2>

- Type: Script Report
- Based on: Equipment Transport
- Roles: System Manager, Card Manager, Card User, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date |  |
| To date | `to_date` | Date |  |
| Project | `project` | Autocomplete |  |


<h2 id="unbilled-card-work">Unbilled Card Work</h2>

- Type: Script Report
- Based on: Card Monthly Card
- Roles: System Manager, Accounts Manager, Card Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Company | `company` | Autocomplete | Yes |
| From date | `from_date` | Date | Yes |
| To date | `to_date` | Date | Yes |
| Billing side | `side` | Select |  |
| Project | `project` | Autocomplete |  |
| Equipment | `equipment` | Link → Card Equipment |  |
| Include cards held by a draft posting | `include_drafts` | Check |  |


<h2 id="worker-custody">Worker Custody</h2>

- Type: Script Report
- Based on: Employee Tool Custody
- Roles: System Manager, Card Manager, Card Supervisor, Card User, Stock Manager, Accounts Manager

| Label | Field name | Type | Required |
|---|---|---|---|
| Employee | `employee` | Link → Employee |  |
