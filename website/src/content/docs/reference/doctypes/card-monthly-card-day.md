---
title: "Card Monthly Card Day"
description: "Fields, layout and permissions of the Card Monthly Card Day DocType."
editUrl: false
sidebar:
  label: "Card Monthly Card Day"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Child table (rows inside another document) |
| Module | Card |


## Fields


**Day details**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Date | `operation_date` | Date |  | Yes |
| Day <small>(read only)</small> | `day_name` | Data |  |  |
| Day status | `day_status` | Select | عمل · إجازة · عطل · توقف من العميل |  |
| Operating hours | `working_hours` | Float |  |  |
| Loads | `loads_count` | Int |  |  |
| Idle reason | `idle_reason` | Data |  |  |


**Downtime**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Stop reason | `stop_reason` | Link | [Card Stop Reason](/card/reference/doctypes/card-stop-reason/) |  |
| Stopped hours | `stopped_hours` | Float |  |  |
| Billable stop <small>(read only)</small> | `reason_billable` | Check |  |  |
| Responsible party | `responsible_party_type` | Select | Company · Supplier · Customer · Other |  |
| Responsible party record | `responsible_party` | Dynamic Link | responsible_party_type |  |
| Responsible party name | `responsible_party_name` | Data |  |  |
| Notes | `notes` | Data |  |  |


**Intake source**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Intake source | `intake_source` | Select | manual · paper · whatsapp · mobile · import |  |
| Intake source key | `intake_source_key` | Data |  |  |
| Intake received on | `intake_received_on` | Datetime |  |  |
| Intake evidence SHA-256 <small>(read only)</small> | `intake_evidence_hash` | Data |  |  |


## Permissions

No own permissions: access follows the parent document.
