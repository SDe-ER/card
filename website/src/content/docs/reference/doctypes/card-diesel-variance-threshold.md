---
title: "Card Diesel Variance Threshold"
description: "Fields, layout and permissions of the Card Diesel Variance Threshold DocType."
editUrl: false
sidebar:
  label: "Card Diesel Variance Threshold"
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
| Company | `company` | Link | Company | Yes |
| Diesel variance % threshold | `variance_pct_threshold` | Percent |  |  |
| Minimum diesel variance (litres) | `min_variance_litres` | Float |  |  |
| Flag diesel fills without operating hours | `flag_fill_without_hours` | Check |  |  |
| Flag operating hours without diesel fills | `flag_hours_without_fill` | Check |  |  |


## Permissions

No own permissions: access follows the parent document.
