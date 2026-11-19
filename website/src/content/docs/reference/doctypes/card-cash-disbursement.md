---
title: "Card Cash Disbursement"
description: "Fields, layout and permissions of the Card Cash Disbursement DocType."
editUrl: false
sidebar:
  label: "Card Cash Disbursement"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page. It follows the main branch, so it can describe changes that are merged but not released yet; see What's new.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/card-cash-disbursement` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company <small>(read only)</small> | `company` | Link | Company | Yes |
| Supplier <small>(read only)</small> | `supplier` | Link | Supplier | Yes |
| Card <small>(read only)</small> | `card` | Link | [Card Monthly Card](/card/reference/doctypes/card-monthly-card/) | Yes |
| Source row <small>(read only)</small> | `adjustment_row` | Data |  | Yes |
| Equipment <small>(read only)</small> | `equipment` | Link | [Card Equipment](/card/reference/doctypes/card-equipment/) |  |
| Project <small>(read only)</small> | `project` | Link | Project |  |
| Amount | `amount` | Currency |  | Yes |
| Payment date | `payment_date` | Date |  | Yes |
| Cash account | `cash_account` | Link | Account | Yes |
| Supporting evidence | `evidence` | Small Text |  | Yes |
| Status <small>(read only)</small> | `status` | Select | Pending · Approved · Posting · Posting Failed · Posted · Cancellation Requested · Cancelled |  |
| Transaction key <small>(read only)</small> | `transaction_key` | Data |  |  |
| Journal Entry <small>(read only)</small> | `journal_entry` | Link | Journal Entry |  |
| Approved by <small>(read only)</small> | `approved_by` | Link | User |  |
| Approved on <small>(read only)</small> | `approved_on` | Datetime |  |  |
| Posted on <small>(read only)</small> | `posted_on` | Datetime |  |  |
| Claimed for posting by <small>(read only)</small> | `posting_claimed_by` | Link | User |  |
| Claimed on <small>(read only)</small> | `posting_claimed_on` | Datetime |  |  |
| Cancellation Reason <small>(read only)</small> | `cancellation_reason` | Small Text |  |  |
| Cancellation Requested By <small>(read only)</small> | `cancellation_requested_by` | Data |  |  |
| Cancellation Requested On <small>(read only)</small> | `cancellation_requested_on` | Datetime |  |  |
| Cancelled By <small>(read only)</small> | `cancelled_by` | Data |  |  |
| Cancelled On <small>(read only)</small> | `cancelled_on` | Datetime |  |  |
| Replaces <small>(read only)</small> | `replaces` | Link | [Card Cash Disbursement](/card/reference/doctypes/card-cash-disbursement/) |  |
| Replacement reason <small>(read only)</small> | `replacement_reason` | Small Text |  |  |
| Posting Error <small>(read only)</small> | `posting_error` | Small Text |  |  |
| Posted By <small>(read only)</small> | `posted_by` | Data |  |  |


## Permissions

| Role | Rights |
|---|---|
| Card Manager | read, write, create, report, export, print |
| Accounts Manager | read, report, print |
| System Manager | read, write, create, delete, report, export, print, email |
