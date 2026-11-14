---
title: "Equipment Operating Group"
description: "Fields, layout and permissions of the Equipment Operating Group DocType."
editUrl: false
sidebar:
  label: "Equipment Operating Group"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/equipment-operating-group` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Group | `group_name` | Data |  | Yes |
| Enabled | `enabled` | Check |  |  |
| Notes | `description` | Small Text |  |  |


**Members**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Members | `members` | Table | [Equipment Operating Group Member](/card/reference/doctypes/equipment-operating-group-member/) |  |


## Child tables

- [Equipment Operating Group Member](/card/reference/doctypes/equipment-operating-group-member/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, report, export, print |
| Card Manager | read, write, create, delete, report, export, print |
| Card Supervisor | read, report |
| Card User | read, report |
| Accounts Manager | read, report |
