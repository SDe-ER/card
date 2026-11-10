---
title: API Overview
description: How to call CARD's server methods and DocTypes over the standard Frappe REST API — authentication, HTTP methods, responses, errors and permission rules.
sidebar:
  order: 1
---

## Overview

CARD has no separate API server. Every CARD endpoint is a Python function marked `@frappe.whitelist` and served by
Frappe's standard REST API, and every CARD record is a DocType reachable through Frappe's standard resource API. The
same permission rules apply as in the Desk and in CARD Mobile: an API caller can do exactly what the same user could do
on screen, never more.

This section lists every whitelisted CARD function, grouped by area. Private helpers that are not whitelisted are not
callable and are not listed.

## Key concepts

| Concept | Meaning |
|---|---|
| Method endpoint | `POST` or `GET` `https://<your-site>/api/method/<dotted.path>` runs a whitelisted function. |
| Resource endpoint | `https://<your-site>/api/resource/<DocType>` lists, reads, creates, updates and deletes records. |
| API key and secret | Generated per user in ERPNext (**User → Settings → API Access → Generate Keys**). The caller acts as that user. |
| Declared HTTP methods | Every CARD function declares `methods=`: `GET` for reads without side effects, `POST` for anything that writes. A few read-only functions accept `POST` because a Desk widget calls them that way. |
| Company scope | The companies a user may see, from User Permissions on Company. Cross-company access is always refused on the server. |

## Features

### Authentication

Use token authentication with the API key and secret of the user the integration runs as:

```bash
curl -s "https://<your-site>/api/method/card.mobile.get_session_context" \
  -H "Authorization: token <api_key>:<api_secret>"
```

- Token requests need no CSRF token.
- A browser session (cookie login) also works; Frappe then requires the `X-Frappe-CSRF-Token` header on `POST`.
- Create a dedicated user for each integration and give it only the roles it needs. Never share keys.

### Calling a method

- **Reads (`GET`)** – pass arguments as query parameters. Lists and objects are sent as JSON strings:

  ```bash
  curl -s -G "https://<your-site>/api/method/card.diesel.get_card_diesel" \
    -H "Authorization: token <api_key>:<api_secret>" \
    --data-urlencode "card=<monthly-card-name>"
  ```

- **Writes (`POST`)** – send a JSON body (or form fields):

  ```bash
  curl -s -X POST "https://<your-site>/api/method/card.cancel_reason.cancel_with_reason" \
    -H "Authorization: token <api_key>:<api_secret>" \
    -H "Content-Type: application/json" \
    -d '{"doctype": "Equipment Transport", "name": "<transport-name>", "reason": "Entered twice"}'
  ```

- A call with an HTTP method the function does not declare is refused with a permission error.

### Responses

A successful call returns HTTP 200 and the function's return value under `message`:

```json
{ "message": { "name": "EQ-0001", "docstatus": 2 } }
```

A function that returns nothing returns `{}` or `{"message": null}`. Reports and file downloads (for example the
supplier statement PDF) return the file itself.

### Errors

Errors use Frappe's standard format: an HTTP status, the exception type, and user-facing messages in
`_server_messages` (a JSON-encoded list of JSON-encoded objects). Messages are translated to the user's language.

| HTTP status | `exc_type` | Typical cause |
|---|---|---|
| 403 | `PermissionError` | Missing role, no read/write right on the record, company not permitted, wrong HTTP method, not logged in. |
| 404 | `DoesNotExistError` | The record does not exist. |
| 417 | `ValidationError` (or a subclass) | A business rule refused the request, for example "Invalid period: end is before start". |
| 409 | `DuplicateEntryError` / timestamp mismatch | Concurrent change of the same record. |

```json
{
  "exc_type": "PermissionError",
  "_server_messages": "[\"{\\\"message\\\": \\\"Not permitted\\\", \\\"indicator\\\": \\\"red\\\"}\"]"
}
```

### Permission rules

- **Roles first.** Each function checks the roles or DocType rights it needs before reading or writing; the required
  role is stated for every endpoint in this reference.
- **Record rights.** Reads and writes go through the user's own permissions (`frappe.get_list`, `check_permission`),
  including User Permissions and permission levels. Fields at a permission level the user lacks are not returned.
- **Company scope.** A company, project, equipment or party of a company the user may not see is refused, never read.
- **Separation of duties.** Some writes refuse the user who prepared the record (for example approving an equipment
  needs review the user edited, or recording the financial decision of a transport the user created).
- **No ledger writes.** No CARD endpoint writes a GL entry. Posting endpoints create draft ERPNext invoices; the
  ledger rows appear only when a person submits them in ERPNext.

### Standard resource API for DocTypes

CARD DocTypes use Frappe's resource API with the same permissions:

| Action | Request |
|---|---|
| List | `GET /api/resource/Card Equipment?fields=["name","equipment_name"]&filters=[["company","=","Example Contracting Co."]]` |
| Read | `GET /api/resource/Card Monthly Card/<name>` |
| Create | `POST /api/resource/Project Diesel Fill` with the document as JSON |
| Update | `PUT /api/resource/Equipment Transport/<name>` with the changed fields |
| Delete | `DELETE /api/resource/<DocType>/<name>` |
| Submit / cancel | `POST /api/method/frappe.client.submit` / `frappe.client.cancel` |

Main CARD DocTypes: Card Equipment, Card Equipment Assignment, Card Monthly Card, Card Daily Log, Project Diesel Fill,
Equipment Transport, Equipment Needs Request, Equipment Needs Review, Employee Tool Custody, Equipment Meter Reading,
Card Equipment Supplier, Card Equipment Customer, Card Stop Reason, Card Settings, Card Company Settings and GL Posting
Log. Server-side validation runs on every route: REST, the Desk form and imports.

:::caution
Records CARD writes from the server only (approval fields, posting logs, settlement links) are refused or ignored when
sent through the resource API. Use the documented methods instead.
:::

## Endpoint groups

| Page | Area |
|---|---|
| [Equipment](/card/api-reference/equipment/) | Units and components, Asset prefill and creation, heatmap, unit integrity. |
| [Cards and daily logs](/card/api-reference/cards-daily-logs/) | Card context, generation from daily logs, cancel with reason, dashboard values. |
| [Diesel](/card/api-reference/diesel/) | Card diesel, fill form helpers, price exceptions, reconciliation filter. |
| [Transport](/card/api-reference/transport/) | Current location, financial decisions. |
| [Materials and needs](/card/api-reference/materials-needs/) | Operator requests, reviews, approval, tool handovers, the Tool Custody screen. |
| [Parties and statements](/card/api-reference/parties-statements/) | Party registry, report filter options and defaults, statement PDF. |
| [Posting and accounting](/card/api-reference/posting-accounting/) | Monthly posting, previews, corrections, invoice and journal links. |
| [Mobile and settings](/card/api-reference/mobile-settings/) | CARD Mobile session, catalog and fitment, Card Settings timeline. |

## Related

- [Reports overview](/card/reports/overview/)
- [Roles and permissions](/card/features/roles-permissions/)
- [CARD Mobile](/card/features/card-mobile/)
