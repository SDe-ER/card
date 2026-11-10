---
title: Diesel API
description: Endpoints for a card's allocated diesel, the diesel fill form helpers, price exceptions and the reconciliation supplier filter.
sidebar:
  order: 4
---

## Overview

Diesel sessions are **Project Diesel Fill** records, read and written with the standard resource API
(`/api/resource/Project Diesel Fill`). The fill's own validation sets the company price, the amount, the review status
and the evidence warnings on every save. The endpoints below give the fill form what fill users may not read
themselves (Card Settings, Project, Cost Center, Supplier), handle the audited price changes of a saved draft, and
expose the diesel allocated to a card.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `card.diesel.get_card_diesel` | Diesel allocated to one monthly card's equipment. |
| GET | `card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable` | Whether the user may change the diesel supplier. |
| GET | `card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query` | Link search for Project, Cost Center and Supplier on the fill form. |
| GET | `card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context` | Company price on a date and the user's price rights. |
| POST | `card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price` | Replace a draft's price with the company price. |
| POST | `card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception` | End a draft's price exception. |
| GET | `card.diesel_reconciliation.diesel_supplier_options` | Supplier options of the Diesel Invoice Reconciliation report. |

## get_card_diesel

`GET /api/method/card.diesel.get_card_diesel`

The diesel allocated to one card's equipment for the card's project and month, with its recorded (direct fill) and
estimated (hours split) parts. Display only: it is never written back and never affects the card's net amount.

**Permission:** read on the monthly card.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `card` | string | Yes | Card Monthly Card name. |

**Returns:** `{"litres", "amount", "litres_recorded", "litres_estimated", "amount_recorded", "amount_estimated",
"company_bears"}` — `company_bears` is true when the equipment's fuel is on the company («الشركة»). A card without
project, month, year or equipment returns zeros.

```bash
curl -s -G "https://<your-site>/api/method/card.diesel.get_card_diesel" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "card=<card-name>"
```

## get_supplier_editable

`GET /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable`

Whether the fill form lets the current user change the diesel supplier. Only this yes/no leaves the server.

**Permission:** read on Project Diesel Fill. **Parameters:** none.

**Returns:** `true` when no default diesel supplier is set in Card Settings; `false` when the supplier policy is fixed
(«ثابت»); otherwise `true` only for the supplier editor role set in Card Settings (Card Manager by default) or the
Administrator.

```bash
curl -s "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable" \
  -H "Authorization: token <api_key>:<api_secret>"
```

## fill_link_query

`GET /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query`

Link search of the fill form for **Project**, **Cost Center** and **Supplier**. Fill users hold no select right on
those masters, so the form searches through this query; it returns names and titles only.

**Permission:** create or write on Project Diesel Fill. Project and Cost Center require the form's company, which must
be one the user may see for diesel fills; the user's User Permissions for diesel fills apply; a user who may not change
the diesel supplier gets the Card Settings supplier only.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `doctype` | string | Yes | `Project`, `Cost Center` or `Supplier`; any other is refused. |
| `txt` | string | Yes | Search text (name or title). |
| `searchfield` | string | Yes | Standard link-query argument. |
| `start` | int | Yes | Offset. |
| `page_len` | int | Yes | Page size. |
| `filters` | object | No | `{"company": "<company>"}` for Project and Cost Center. |

**Returns:** a list of `[name, title]` pairs (cost centers: leaf and enabled only; suppliers: enabled only).

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "doctype=Project" --data-urlencode "txt=" --data-urlencode "searchfield=name" \
  --data-urlencode "start=0" --data-urlencode "page_len=20" \
  --data-urlencode 'filters={"company":"Example Contracting Co."}'
```

## get_diesel_price_context

`GET /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context`

What the fill form needs before saving: the company diesel price on the fill date and whether the user may grant a
price exception or a zero price.

**Permission:** read on Project Diesel Fill; a company the user may not see returns an empty context.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `company` | string | No | Company of the fill. |
| `date` | date | No | Fill date; today when empty. |

**Returns:** `{"price": <number>, "can_except": bool, "can_zero": bool, "exception_role": "<role or null>"}`.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "company=Example Contracting Co." --data-urlencode "date=2026-01-15"
```

## use_company_price

`POST /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price`

On a saved draft without a price exception, replaces the price with the current company price.

**Permission:** write on the fill and the **diesel price exception role** set in Card Settings.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Draft Project Diesel Fill. |
| `reason` | string | Yes | Why the price changes (an empty reason is refused). |

**Returns:** `{"unit_price": <number>, "price_source": "<source>"}`. **Side effects:** saves the fill; the change is
audited with the reason as a comment on the fill.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"name": "<fill-name>", "reason": "Price entered by mistake"}'
```

## remove_price_exception

`POST /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception`

Ends the price exception of a saved draft: it returns to the current company price.

**Permission:** write on the fill and the diesel price exception role.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Draft fill with a price exception. |
| `reason` | string | Yes | Written reason. |

**Returns:** `{"unit_price", "price_source"}`. **Side effects:** clears the exception, saves, audits the change.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"name": "<fill-name>", "reason": "Supplier agreed to the company price"}'
```

## diesel_supplier_options

`GET /api/method/card.diesel_reconciliation.diesel_supplier_options`

Options for the supplier filter of the [Diesel Invoice Reconciliation](/card/reports/diesel-fuel/#diesel-invoice-reconciliation)
report: suppliers of the diesel sessions the user may read, in the companies the user may see for both Project Diesel
Fill and Purchase Invoice.

**Permission:** a CARD report role, the report's own roles, and role read on Project Diesel Fill and Purchase Invoice.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `txt` | string | No | Search text. |
| `company` | string | No | Limit to one company. |

**Returns:** up to 50 `{"value": "<supplier>", "description": ""}` objects.

```bash
curl -s -G "https://<your-site>/api/method/card.diesel_reconciliation.diesel_supplier_options" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "company=Example Contracting Co."
```

## Related

- [Diesel](/card/features/diesel/)
- [Diesel and fuel reports](/card/reports/diesel-fuel/)
