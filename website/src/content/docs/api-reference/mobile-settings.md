---
title: Mobile and Settings API
description: Endpoints for the CARD Mobile session, the parts catalog and fitment, and the company-scoped Card Settings timeline.
sidebar:
  order: 9
---

## Overview

**CARD Mobile** (`/cdms`) uses the same Frappe login, session and CSRF protection as the Desk, and calls the same
endpoints as every other client; each endpoint keeps its own permission checks. This page lists the endpoints that only
the mobile app and the catalog use, plus CARD's overrides of the Desk form loader that keep the **Card Settings**
timeline within the user's companies. The operator request endpoints are on the
[Materials and needs](/card/api-reference/materials-needs/) page.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `card.mobile.get_session_context` | The signed-in user's CARD Mobile context. |
| GET | `card.catalog.search` | One page of the parts catalog, optionally with the fit for a machine. |
| GET | `card.catalog.filter_options` | Values for the Item Group or Brand filter. |
| GET | `card.fitment.fit_for` | The fit of up to 50 items for one machine. |
| GET | `card.fitment.machines` | Machines the caller may look up in the catalog. |
| GET, POST | `card.card.doctype.card_settings.card_settings.getdoc` | Override of `frappe.desk.form.load.getdoc`. |
| GET, POST | `card.card.doctype.card_settings.card_settings.get_docinfo` | Override of `frappe.desk.form.load.get_docinfo`. |

## Catalog users

The catalog endpoints accept any logged-in user who may read Items, or who holds a catalog role: Card Operator, Card
Supervisor, Card Manager, System Manager (portal roles) or Card User (read-only catalog viewer). With a machine, the
caller must also read that machine, or operate it as a Card Operator.

## get_session_context

`GET /api/method/card.mobile.get_session_context`

**Permission:** a portal role, or a read-only catalog viewer (a Card User without a portal role). Reads only.
**Parameters:** none.

**Returns:** `{"user", "full_name", "roles" (the user's CARD portal roles), "employee" ({name, employee_name, company} of
the linked active Employee, or null), "catalog_only": bool, "card_version"}`.

```bash
curl -s "https://<your-site>/api/method/card.mobile.get_session_context" -H "Authorization: token <api_key>:<api_secret>"
```

## search

`GET /api/method/card.catalog.search`

One page of the ERPNext item catalogue for the search text (item code, item name, barcode, OEM number — codes from 3
characters) and the filters. The user's own Item rights and User Permissions apply. No total count is given.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `txt` | string | No | Search text (at most 140 characters used). |
| `item_group` | string | No | Item group, including its sub-groups; an unknown group lists nothing. |
| `brand` | string | No | Brand. |
| `start` | int | No | Offset (default 0). |
| `page_length` | int | No | Page size, default 20, at most 50. |
| `equipment` | string | No | Machine: every item then carries its fit for it. |
| `fits` | int | No | With `equipment`, `1` lists only items confirmed for the machine or its model. |

**Returns:** `{"items": [{"item_code", "item_name", "stock_uom", "image", "item_group", "item_group_label", "brand",
"oem": [...], "alternatives": [{"item_code", "item_name"}], "fit", "fit_model"}], "has_more": bool}`. `fit` is one of
`confirmed_machine`, `confirmed_model`, `not_compatible`, `pending`, `unknown`; a machine's own decision wins over its
model's, and a pending row is never a fit.

```bash
curl -s -G "https://<your-site>/api/method/card.catalog.search" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "txt=oil filter" --data-urlencode "equipment=EQ-0001"
```

## filter_options

`GET /api/method/card.catalog.filter_options`

Values for the Item Group or Brand filter, searched and paged on the server with the user's rights. Item groups are
matched by name or by their translation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `kind` | string | Yes | `item_group` or `brand`. |
| `txt` | string | No | Search text. |
| `start` | int | No | Offset. |
| `page_length` | int | No | Page size (default 20, at most 50). |

**Returns:** a list of `{"value", "label"}`.

```bash
curl -s -G "https://<your-site>/api/method/card.catalog.filter_options" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "kind=brand"
```

## fit_for

`GET /api/method/card.fitment.fit_for`

The fit of up to 50 items for one machine, for the inline item picker of CARD Mobile. Only items the caller may list in
the catalog are answered.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `equipment` | string | Yes | Machine. |
| `items` | list | Yes | Item codes (JSON list, at most 50). |

**Returns:** `{<item_code>: {"fit": "<state>", "fit_model": "<model name or null>"}}`.

```bash
curl -s -G "https://<your-site>/api/method/card.fitment.fit_for" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "equipment=EQ-0001" --data-urlencode 'items=["<item-code-1>","<item-code-2>"]'
```

## machines

`GET /api/method/card.fitment.machines`

Machines the caller may look up in the catalog: a Desk reader's own list (his permissions apply; ended equipment is
left out), or an operator's own machines. Searched and paged on the server.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `txt` | string | No | Search text (name or equipment name). |
| `start` | int | No | Offset; pages of 20. |

**Returns:** `{"machines": [{"name", "equipment_name", "model"}], "has_more": bool}`.

```bash
curl -s -G "https://<your-site>/api/method/card.fitment.machines" -H "Authorization: token <api_key>:<api_secret>"
```

## Other: Card Settings timeline overrides

CARD registers two `override_whitelisted_methods` so that a company-restricted user never sees, in the **Card Settings**
form timeline, a change to a row of another company:

| Overridden method | CARD function | Parameters |
|---|---|---|
| `frappe.desk.form.load.getdoc` | `card.card.doctype.card_settings.card_settings.getdoc` | `doctype`, `name` |
| `frappe.desk.form.load.get_docinfo` | `card.card.doctype.card_settings.card_settings.get_docinfo` | `doc` or `doctype` + `name` |

Each override first calls the override registered before CARD's by another app (or Frappe's own method), so the chain
is kept, then removes from `docinfo.versions` every change of a row of a company the user may not read. Responses for
every other DocType are unchanged. Clients keep calling the standard Frappe paths; there is no reason to call the CARD
functions directly.

```bash
curl -s -G "https://<your-site>/api/method/frappe.desk.form.load.getdoc" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "doctype=Card Settings" --data-urlencode "name=Card Settings"
```

## Related

- [CARD Mobile](/card/features/card-mobile/)
- [Maintenance and parts](/card/features/maintenance-parts/)
- [Configuration](/card/getting-started/configuration/)
