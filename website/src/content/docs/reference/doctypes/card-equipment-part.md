---
title: "Card Equipment Part"
description: "Fields, layout and permissions of the Card Equipment Part DocType."
editUrl: false
sidebar:
  label: "Card Equipment Part"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/card-equipment-part` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Part item | `item_code` | Link | Item | Yes |
| Applies to | `applies_to` | Select | Equipment Model · Equipment | Yes |
| Equipment model | `equipment_model` | Link | [Card Equipment Model](/card/reference/doctypes/card-equipment-model/) |  |
| Equipment | `card_equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |
| Compatibility status | `compatibility_status` | Select | Pending Technical Review · Confirmed · Not Compatible | Yes |
| Review stage <small>(read only)</small> | `review_stage` | Select | Pending Second Review |  |
| Decision reason | `decision_reason` | Small Text |  |  |
| Active | `is_active` | Check |  |  |


**Fitment evidence**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Evidence source | `evidence_source` | Select | Maker parts book · Maker or dealer catalogue · Supplier or dealer confirmation · Physical check on the machine · Installation record · Other |  |
| Evidence reference | `evidence_reference` | Data |  |  |
| Evidence file | `evidence_file` | Attach |  |  |
| Quantity per use | `qty_per_use` | Float |  |  |
| Technical notes | `technical_notes` | Small Text |  |  |


**Review record**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Proposed by <small>(read only)</small> | `proposed_by` | Link | User |  |
| Proposed on <small>(read only)</small> | `proposed_on` | Datetime |  |  |
| First review by <small>(read only)</small> | `first_review_by` | Link | User |  |
| First review on <small>(read only)</small> | `first_review_on` | Datetime |  |  |
| First review decision <small>(read only)</small> | `first_review_decision` | Select | Confirmed · Not Compatible |  |
| First review reason <small>(read only)</small> | `first_review_reason` | Small Text |  |  |
| Decided by <small>(read only)</small> | `confirmed_by` | Link | User |  |
| Decided on <small>(read only)</small> | `confirmed_on` | Datetime |  |  |
| Retired by <small>(read only)</small> | `retired_by` | Link | User |  |
| Retired on <small>(read only)</small> | `retired_on` | Datetime |  |  |
| Retire reason | `retire_reason` | Small Text |  |  |
| Source <small>(read only)</small> | `source` | Select | Manual · Supervisor proposal · Approved request · Installation |  |
| Source request <small>(read only)</small> | `source_request` | Link | [Equipment Needs Request](/card/reference/doctypes/equipment-needs-request/) |  |
| Company <small>(read only)</small> | `company` | Link | Company |  |
| Compatibility key <small>(hidden, read only)</small> | `compat_key` | Data |  |  |


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, report, export, print |
| Card Manager | read, write, create, report, export, print |
| Card Supervisor | read, write, create, report, print |
