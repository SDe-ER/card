---
title: "Card Period Run"
description: "Fields, layout and permissions of the Card Period Run DocType."
editUrl: false
sidebar:
  label: "Card Period Run"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Submittable (Draft → Submitted → Cancelled) |
| Module | Card |
| Open in Desk | `/app/card-period-run` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Period run month | `month` | Select | 01 · 02 · 03 · 04 · 05 · 06 · 07 · 08 · 09 · 10 · 11 · 12 | Yes |
| Period run year | `year` | Int |  | Yes |
| Period run version <small>(read only)</small> | `version` | Int |  |  |
| Period run self-approval rule | `self_approval_rule` | Select | Warn only (period run) · Refuse (period run) |  |
| Period run approval <small>(read only)</small> | `approval_status` | Select | Pending · Approved · Returned for correction |  |
| Period run submitted by <small>(read only)</small> | `submitted_by` | Link | User |  |
| Period run edited by <small>(hidden, read only)</small> | `edited_by` | Small Text |  |  |
| Period run approved by <small>(read only)</small> | `approved_by` | Link | User |  |
| Period run approved on <small>(read only)</small> | `approved_on` | Datetime |  |  |
| Period run approved version <small>(read only)</small> | `approved_version` | Int |  |  |
| Approved snapshot fingerprint <small>(hidden, read only)</small> | `approved_hash` | Data |  |  |
| Approved by its own preparer <small>(read only)</small> | `self_approved` | Check |  |  |
| Period run return reason <small>(read only)</small> | `return_reason` | Small Text |  |  |
| Period run returned by <small>(read only)</small> | `returned_by` | Link | User |  |
| Period run returned on <small>(read only)</small> | `returned_on` | Datetime |  |  |


**Period run snapshot**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Snapshot built on <small>(read only)</small> | `built_on` | Datetime |  |  |
| Snapshot fingerprint <small>(read only)</small> | `snapshot_hash` | Data |  |  |
| Period run currency <small>(read only)</small> | `currency` | Link | Currency |  |
| Diesel price VAT basis at build <small>(read only)</small> | `diesel_vat_basis` | Data |  |  |
| Period run fingerprint version <small>(hidden, read only)</small> | `fingerprint_version` | Int |  |  |
| Source documents in the run <small>(read only)</small> | `source_count` | Int |  |  |
| Supplier-side documents <small>(read only)</small> | `supplier_source_count` | Int |  |  |
| Supplier-side gross source total <small>(read only)</small> | `supplier_total` | Currency | currency |  |
| Customer-side documents <small>(read only)</small> | `customer_source_count` | Int |  |  |
| Customer-side gross source total <small>(read only)</small> | `customer_total` | Currency | currency |  |


**Period run source documents**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Period run source documents <small>(read only)</small> | `sources` | Table | [Card Period Run Source](/card/reference/doctypes/card-period-run-source/) |  |
| Amended From <small>(read only)</small> | `amended_from` | Link | [Card Period Run](/card/reference/doctypes/card-period-run/) |  |


## Child tables

- [Card Period Run Source](/card/reference/doctypes/card-period-run-source/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, submit, cancel, amend, report, export, print, email |
| Card Manager | read, write, create, submit, cancel, amend, report, export, print |
| Accounts Manager | read, write, submit, cancel, report, export, print |
| System Manager (permlevel 1) | read |
| Card Manager (permlevel 1) | read |
| Accounts Manager (permlevel 1) | read |
