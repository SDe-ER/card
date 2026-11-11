---
title: "GL Posting Log"
description: "Fields, layout and permissions of the GL Posting Log DocType."
editUrl: false
sidebar:
  label: "GL Posting Log"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/gl-posting-log` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Party type | `party_type` | Select | Supplier · Customer | Yes |
| Party | `party` | Dynamic Link | party_type | Yes |
| Month | `month` | Data |  | Yes |
| Year | `year` | Int |  | Yes |
| Posting type | `posting_type` | Select | Purchase Invoice · Sales Invoice · Journal Entry | Yes |
| Status <small>(read only)</small> | `status` | Select | Draft · Submitted · Cancelled · Failed | Yes |


**Posting document**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Posting DocType <small>(read only)</small> | `posting_doctype` | Data |  |  |
| Posting document <small>(read only)</small> | `posting_doc` | Dynamic Link | posting_doctype |  |
| Amount <small>(read only)</small> | `amount` | Currency |  |  |
| Posting key <small>(read only)</small> | `posting_key` | Data |  |  |
| Failure reason | `failure_reason` | Small Text |  |  |
| Remarks | `remarks` | Small Text |  |  |
| Sequence <small>(read only)</small> | `sequence` | Int |  |  |
| Sources <small>(read only)</small> | `sources` | Table | [GL Posting Source](/card/reference/doctypes/gl-posting-source/) |  |
| Origin <small>(read only)</small> | `origin` | Select | Built · Linked |  |


**Integrity**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Built signature <small>(read only)</small> | `built_signature` | Data |  |  |
| Lines signature <small>(read only)</small> | `lines_signature` | Data |  |  |
| Built snapshot <small>(hidden, read only)</small> | `built_snapshot` | Long Text |  |  |
| Accepted correction signature <small>(read only)</small> | `accepted_signature` | Data |  |  |
| Correction accepted by <small>(read only)</small> | `accepted_by` | Link | User |  |
| Correction reason <small>(read only)</small> | `correction_reason` | Small Text |  |  |
| Supplier invoices reviewed as unrelated <small>(read only)</small> | `reviewed_invoices` | Small Text |  |  |
| Open difference (linked invoice) <small>(read only)</small> | `link_difference` | Currency |  |  |


## Child tables

- [GL Posting Source](/card/reference/doctypes/gl-posting-source/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, report, export, print, email |
| Accounts Manager | read, report, export, print, email |
| Card Manager | read, report, print |
