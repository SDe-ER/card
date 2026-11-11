---
title: "Card Equipment Model"
description: "Fields, layout and permissions of the Card Equipment Model DocType."
editUrl: false
sidebar:
  label: "Card Equipment Model"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/card-equipment-model` |


## Fields

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Model name | `model_name` | Data |  | Yes |
| Equipment make | `equipment_make` | Link | [Card Equipment Make](/card/reference/doctypes/card-equipment-make/) | Yes |
| Equipment type | `equipment_type` | Link | [Card Equipment Type](/card/reference/doctypes/card-equipment-type/) | Yes |
| Disabled | `disabled` | Check |  |  |
| Description | `description` | Small Text |  |  |
| Model key <small>(hidden, read only)</small> | `model_key` | Data |  |  |


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, report, export, print |
| Card Manager | read, write, create, report, export, print |
| Card Supervisor | read, report, print |
| Card User | read, report, print |
| Accounts Manager | read, report, print |
