---
title: Materials and Needs API
description: Endpoints for operator requests, supervisor reviews, management approval, tool handovers and the Tool Custody screen.
sidebar:
  order: 6
---

## Overview

Equipment needs flow in three steps: an operator asks for parts or tools for his machine (**Equipment Needs Request**),
a supervisor consolidates the requests of a project (**Equipment Needs Review**), and management approves the review
into draft ERPNext Material Requests and draft tool handovers. Tool custody (**Employee Tool Custody**) then records
every handover, return and transfer, confirmed by the store side. The endpoints below drive the operator page, the
review form and the Tool Custody screen; every write goes through the user's own rights.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `card.materials.get_portal_context` | The operator's machines and recent requests. |
| GET | `card.materials.search_items` | Items an operator may pick (20 at most). |
| POST | `card.materials.submit_needs` | Submit the operator's request for one of his machines. |
| GET | `card.materials.review_stock` | Live stock hint per review line. |
| POST | `card.materials.pull_requests` | Add the pending request lines of the project to a draft review. |
| POST | `card.materials.approve_review` | Approve a submitted review into draft Material Requests and handovers. |
| POST | `card.materials.close_tool_handover` | Close an awaiting handover the worker did not take. |
| POST | `card.materials.make_tool_handover` | Make a replacement handover draft for an approved tool line. |
| GET | `card.tool_custody.context` | Tabs, default tab and buttons of the Tool Custody screen. |
| GET | `card.tool_custody.view` | One page of a screen tab (awaiting, held, history). |
| GET | `card.tool_custody.employee_query` | Link query: employees for the screen. |
| GET | `card.tool_custody.employee_company` | Company of an employee the screen may offer. |
| GET | `card.tool_custody.store_query` | Link query: stores (warehouses). |
| GET | `card.tool_custody.item_query` | Link query: stock tools. |
| POST | `card.tool_custody.move` | New draft movement (Handover, Return, Transfer). |
| POST | `card.tool_custody.confirm` | Confirm (submit) a waiting movement. |

## Roles used on this page

| Role group | Roles |
|---|---|
| Portal roles (operator page, CARD Mobile requests) | Card Operator, Card Supervisor, Card Manager, System Manager |
| Approvers | Card Manager, System Manager |
| Tool Custody screen | Card Supervisor, Card Manager, Stock Manager, System Manager (with read on Employee Tool Custody) |
| Store side | Users who may submit both Employee Tool Custody and Stock Entry |

## get_portal_context

`GET /api/method/card.materials.get_portal_context` — **Permission:** a portal role. **Parameters:** none.

**Returns:** `{"employee": "<employee or null>", "allowed": bool, "machines": [{"name", "equipment_name", "project"}],
"requests": [...]}` — the 20 most recent requests of the operator, each with its `items` (kind, item code,
description, quantity).

```bash
curl -s "https://<your-site>/api/method/card.materials.get_portal_context" -H "Authorization: token <api_key>:<api_secret>"
```

## search_items

`GET /api/method/card.materials.search_items` — **Permission:** a portal role.

Items by code, name, barcode or OEM number, with the same rules and User Permissions as the catalog search. Operators
have no Item read permission; this is the one deliberate exception.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `txt` | string | No | Search text (at most 140 characters are used). |

**Returns:** up to 20 `{"item_code", "item_name", "stock_uom"}`.

```bash
curl -s -G "https://<your-site>/api/method/card.materials.search_items" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "txt=filter"
```

## submit_needs

`POST /api/method/card.materials.submit_needs` — **Permission:** a portal role and an account linked to an Employee.

Creates and submits the operator's own Equipment Needs Request for one of his machines, dated today.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `equipment` | string | Yes | The operator's machine. |
| `items` | list | Yes | Rows: `kind` (`Part` or `Tool`), `item_code` (optional), `description` (140 chars), `qty`, `reason` (140 chars), `fit_reason` (500 chars). |
| `notes` | string | No | Request notes. |

**Returns:** the request name. **Side effects:** inserts and submits the request; the request's validation applies
(machine of the operator, repeat check, fit).

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.submit_needs" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"equipment": "EQ-0001", "items": [{"kind": "Part", "item_code": "<item-code>", "qty": 2, "reason": "Worn"}]}'
```

## review_stock

`GET /api/method/card.materials.review_stock` — **Permission:** read on the review.

The stock hint per review line, read live with the reader's rights and never stored on the review.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `review` | string | Yes | Equipment Needs Review name. |

**Returns:** `{<review line name>: <quantity or null>}`; `{}` for a user who may not read stock. A line without an item,
or in a warehouse the reader may not see, has no hint.

```bash
curl -s -G "https://<your-site>/api/method/card.materials.review_stock" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "review=<review-name>"
```

## pull_requests

`POST /api/method/card.materials.pull_requests` — **Permission:** write on the review; the review must be a draft.

Adds every submitted, pending request line of the review's project (within its dates, if set) that no other review
holds. Requested quantities are copied, never edited; the approved quantity starts equal to the requested one, the
route is "From store" with the company's store warehouse.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `review` | string | Yes | Draft Equipment Needs Review. |

**Returns:** the number of lines added. **Side effects:** saves the review.

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.pull_requests" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" -d '{"review": "<review-name>"}'
```

## approve_review

`POST /api/method/card.materials.approve_review`

Management approval of a submitted review. Every approved line goes into a **draft** ERPNext Material Request
(Purchase for "Buy for project" lines, Material Issue for parts from the store) with item, project, cost center and the
equipment dimension on part rows. Every approved tool line gets a **draft** custody Handover for its worker. Approval
moves no stock and gives nobody a tool.

**Permission:** Card Manager or System Manager; create on Material Request (for example Stock User); create on Employee
Tool Custody when the review has tools; read on the review. **Separation of duties:** nobody who reviewed, edited or
submitted the review may approve it — no role is exempt.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `review` | string | Yes | Submitted Equipment Needs Review, not yet approved. |

**Returns:** the list of Material Requests created. **Side effects:** inserts draft Material Requests and handovers,
sets the review to Approved with the approver and time, and marks each request Approved or Rejected. Refused when a
line has no item or no warehouse, a tool is not a stock item or is a fixed asset, a tool line names no worker, or no
tool custody store is set in Card Settings.

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.approve_review" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" -d '{"review": "<review-name>"}'
```

## close_tool_handover

`POST /api/method/card.materials.close_tool_handover`

The worker did not take the tool: the awaiting draft handover is closed with a reason, never submitted; nothing is
counted or moved.

**Permission:** write on the custody record, and Card Manager or the store side. A user may not close a handover to
himself.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `custody` | string | Yes | Draft Employee Tool Custody of an approved review line, "Awaiting handover". |
| `reason` | string | Yes | Why the tool was not handed over. |

**Returns:** the custody name. **Side effects:** sets the handover status to "Not handed over" with the reason.

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.close_tool_handover" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"custody": "<custody-name>", "reason": "Worker on leave"}'
```

## make_tool_handover

`POST /api/method/card.materials.make_tool_handover` — **Permission:** Card Manager; read on the review.

A replacement draft for the tools of an approved line that are not handed over yet, after a closed or cancelled
handover.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `review_item` | string | Yes | Equipment Needs Review Item (a tool line of an approved review). |

**Returns:** the new custody draft name. Refused when a handover of the line is already awaiting, all tools are handed
over, or the line changed meanwhile.

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.make_tool_handover" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" -d '{"review_item": "<line-name>"}'
```

## Tool Custody screen: context

`GET /api/method/card.tool_custody.context` — **Permission:** a screen role and read on Employee Tool Custody.
**Parameters:** none.

**Returns:** `{"tabs": ["awaiting", "held", "history"], "default_tab", "can_confirm", "can_prepare", "default_store",
"default_stores": {<company>: <store>}}`. The store side and managers open on "awaiting", others on "held".

```bash
curl -s "https://<your-site>/api/method/card.tool_custody.context" -H "Authorization: token <api_key>:<api_secret>"
```

## Tool Custody screen: view

`GET /api/method/card.tool_custody.view` — **Permission:** as `context`. Reads only through the user's own list
permissions.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tab` | string | No | `awaiting` (default), `held` or `history`. |
| `employee` | string | No | Filter by worker (as sender or receiver). |
| `item_code` | string | No | Filter by tool. |
| `start` | int | No | Offset; pages of 25. |

**Returns:** `{"tab", "rows": [...], "more": bool, "start"}`. Awaiting rows carry the store stock, `waiting_for_stock`,
`has_serial_no` and the allowed `actions` (`confirm`, `not_handed`, `replace`); held rows carry `actions` (`return`,
`transfer`). A user never gets an action on his own custody.

```bash
curl -s -G "https://<your-site>/api/method/card.tool_custody.view" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "tab=held"
```

## Tool Custody screen: link queries

`employee_query`, `store_query` and `item_query` are standard link queries (`doctype`, `txt`, `searchfield`, `start`,
`page_len`, `filters`), all `GET` and limited to the screen roles. `employee_company` returns one employee's company.

| Endpoint | Returns | Filters |
|---|---|---|
| `card.tool_custody.employee_query` | `[name, employee_name]` of active employees in the user's custody companies and Employee User Permissions | `company`, `exclude` (the worker himself), `any_status` (include inactive) |
| `card.tool_custody.store_query` | `[name, warehouse_name]` of enabled, non-group warehouses in those companies | `company` |
| `card.tool_custody.item_query` | `[item_code, item_name]` of enabled stock items that are not fixed assets | ignored |
| `card.tool_custody.employee_company` (`employee`) | `{"company": "<company>"}` | — |

```bash
curl -s -G "https://<your-site>/api/method/card.tool_custody.employee_company" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "employee=<employee-id>"
```

## Tool Custody screen: move

`POST /api/method/card.tool_custody.move` — **Permission:** a screen role and create on Employee Tool Custody for the
worker's company.

A new movement saved as a draft with defaults: the store of the worker's company (else the site's main store) and, for
a Handover, the worker's machine and its project. It is confirmed with `confirm` after its receipt is printed and
signed.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `movement` | string | Yes | `Handover`, `Return` or `Transfer`. |
| `employee` | string | Yes | The worker. |
| `item_code` | string | Yes | Tool item. |
| `qty` | float | Yes | Quantity. |
| `to_employee` | string | For Transfer | Receiving worker. |
| `warehouse` | string | No | Store; default as above (not used for a Transfer). |
| `serial_no` | string | No | Serial number. |

**Returns:** `{"name", "may_confirm", "has_serial_no", "employee_name", "to_employee_name"}`.

```bash
curl -s -X POST "https://<your-site>/api/method/card.tool_custody.move" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"movement": "Handover", "employee": "<employee-id>", "item_code": "<item-code>", "qty": 1}'
```

## Tool Custody screen: confirm

`POST /api/method/card.tool_custody.confirm` — **Permission:** a screen role and submit on the custody record; the
controller's own rules (store-side confirmation, signed receipt, separation of duties, stock) decide.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `custody` | string | Yes | Draft Handover, Return or Transfer. |
| `receipt` | string | No | The signed receipt file. |
| `qty` | float | No | Final quantity, more than zero. |
| `serial_no` | string | No | Serial number. |

**Returns:** `{"name", "stock_entry"}`. **Side effects:** submits the movement; a confirmed Handover or Return creates
and submits its Stock Entry in the same transaction.

```bash
curl -s -X POST "https://<your-site>/api/method/card.tool_custody.confirm" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"custody": "<custody-name>", "receipt": "/private/files/receipt.pdf"}'
```

## Related

- [Equipment needs](/card/features/equipment-needs/)
- [Tool custody](/card/features/tool-custody/)
- [Operations reports](/card/reports/operations/)
