---
title: "Card Monthly Card Adjustment"
description: "Fields, layout and permissions of the Card Monthly Card Adjustment DocType."
editUrl: false
sidebar:
  label: "Card Monthly Card Adjustment"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page. It follows the main branch, so it can describe changes that are merged but not released yet; see What's new.
:::

| | |
|---|---|
| Kind | Child table (rows inside another document) |
| Module | Card |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Cash paid | `is_cash_disbursement` | Check |  |  |
| Cash payment status <small>(read only)</small> | `cash_status` | Data |  |  |
| Cash payment <small>(read only)</small> | `cash_payment` | Link | [Card Cash Disbursement](/card/reference/doctypes/card-cash-disbursement/) |  |
| Journal Entry <small>(read only)</small> | `cash_journal_entry` | Link | Journal Entry |  |
| Cash account for the owner-paid expense | `cash_account` | Link | Account |  |
| Adjustment date | `adjustment_date` | Date |  | Yes |
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
