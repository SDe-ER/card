---
title: "GL Posting Source"
description: "Fields, layout and permissions of the GL Posting Source DocType."
editUrl: false
sidebar:
  label: "GL Posting Source"
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
| Source doctype | `source_doctype` | Select | Card Monthly Card · Project Diesel Fill · Equipment Transport | Yes |
| Source | `source_name` | Dynamic Link | source_doctype | Yes |
| Amount | `amount` | Currency |  |  |


## Permissions

No own permissions: access follows the parent document.
