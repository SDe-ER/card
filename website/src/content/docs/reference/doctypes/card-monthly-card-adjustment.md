---
title: "Card Monthly Card Adjustment"
description: "Fields, layout and permissions of the Card Monthly Card Adjustment DocType."
editUrl: false
sidebar:
  label: "Card Monthly Card Adjustment"
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
| Type | `adjustment_type` | Select | إضافة · خصم | Yes |
| Description | `description` | Data |  | Yes |
| Amount | `amount` | Currency |  | Yes |
| Adjustment type | `adjustment_type_ref` | Data |  |  |
| Side | `side` | Select | Supplier · Customer |  |


**Downtime charge**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Stop reason | `stop_reason` | Link | [Card Stop Reason](/card/reference/doctypes/card-stop-reason/) |  |
| Agreement reference | `agreement_reference` | Data |  |  |
| Responsible party | `responsible_party_type` | Select | Company · Supplier · Customer · Other |  |
| Responsible party record | `responsible_party` | Dynamic Link | responsible_party_type |  |
| Responsible party name | `responsible_party_name` | Data |  |  |


## Permissions

No own permissions: access follows the parent document.
