---
title: Parties and Statements API
description: Endpoints for the supplier and customer registry, the report filter options and defaults, and the supplier statement PDF.
sidebar:
  order: 7
---

## Overview

CARD keeps a registry row for every equipment supplier (**Card Equipment Supplier**) and customer (**Card Equipment
Customer**) named after the ERPNext party. The registry stores no figures: a row is shared by every company, so any
stored total would expose other companies' activity. Figures are computed on request for the companies the caller may
see. The endpoints below serve the registry, the filters of the CARD reports and the supplier statement PDF.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `card.api.party_figures` | Per-company figures of one registry party. |
| POST | `card.api.refresh_supplier` | Sync the supplier registry rows. |
| POST | `card.api.refresh_customer` | Sync the customer registry rows. |
| GET | `card.api.card_suppliers_query` | Link query: registry suppliers with cards. |
| GET | `card.api.card_customers_query` | Link query: registry customers with cards. |
| GET, POST | `card.api.card_company_options` | Company filter options of the reports. |
| GET, POST | `card.api.card_project_options` | Project filter options of the reports. |
| GET | `card.api.report_defaults` | Report filter defaults from Card Settings. |
| POST | `card.card.report.equipment_supplier_statement.statement_pdf.download_pdf` | Supplier statement as an A4 PDF. |

## party_figures

`GET /api/method/card.api.party_figures`

Per-company figures of one registry party: the supplier net, or the customer accrued amount (customer net), from
submitted cards, for the permitted companies only.

**Permission:** a CARD report role and read on the registry row.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `party_type` | string | Yes | `Supplier` or `Customer`. |
| `party` | string | Yes | Registry row name (the party's name). |

**Returns:** a list per company of `{"company", "equipment_count", "card_count", "total_hours", "total", "first_month",
"last_month"}` (months as `YYYY-MM`).

```bash
curl -s -G "https://<your-site>/api/method/card.api.party_figures" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "party_type=Supplier" --data-urlencode "party=Supplier A"
```

## refresh_supplier and refresh_customer

`POST /api/method/card.api.refresh_supplier` · `POST /api/method/card.api.refresh_customer`

Make sure one party — or every party with submitted cards on its side (suppliers: non-owned cards; customers: billing
cards) — has its registry row, named after the party, with no stored figures. A row left misnamed by an earlier rename
is realigned.

**Permission:** System Manager only.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `supplier` / `customer` | string | No | One party; when empty, all parties. |

**Returns:** a list of `{"supplier": "<name>"}` / `{"customer": "<name>"}`. **Side effects:** inserts, renames or
saves registry rows.

```bash
curl -s -X POST "https://<your-site>/api/method/card.api.refresh_supplier" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" -d '{"supplier": "Supplier A"}'
```

## card_suppliers_query and card_customers_query

`GET /api/method/card.api.card_suppliers_query` · `GET /api/method/card.api.card_customers_query`

Link queries of the statement filters: registry rows with at least one draft or submitted card in a company the user
may see. The filter links to the registry because every report role may read it, while operational roles cannot read
Supplier or Customer.

**Permission:** a CARD report role.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `doctype` | string | Yes | Standard link-query argument. |
| `txt` | string | Yes | Search text (name or party name). |
| `searchfield` | string | Yes | Standard link-query argument. |
| `start` | int | Yes | Offset. |
| `page_len` | int | Yes | Page size. |
| `filters` | object | Yes | `{"company": "<company>"}` (optional company; one the user may not see returns nothing). |

**Returns:** a list of `[name, supplier_name]` or `[name, customer_name]`.

```bash
curl -s -G "https://<your-site>/api/method/card.api.card_suppliers_query" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "doctype=Card Equipment Supplier" --data-urlencode "txt=" --data-urlencode "searchfield=name" \
  --data-urlencode "start=0" --data-urlencode "page_len=20" --data-urlencode 'filters={"company":"Example Contracting Co."}'
```

## card_company_options

`GET|POST /api/method/card.api.card_company_options`

Options for the reports' Company filter: the companies the user may see. Read only (`POST` is accepted because the
Autocomplete control posts).

**Permission:** a CARD report role.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `txt` | string | No | Case-insensitive search text. |

**Returns:** up to 50 company names.

```bash
curl -s -G "https://<your-site>/api/method/card.api.card_company_options" -H "Authorization: token <api_key>:<api_secret>"
```

## card_project_options

`GET|POST /api/method/card.api.card_project_options`

Options for the reports' Project filter: projects of the companies the user may see. Read only.

**Permission:** a CARD report role.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `txt` | string | No | Search text (record name or project name). |
| `company` | string | No | Limit to one company. |

**Returns:** up to 50 `{"value": "PROJ-0001", "label": "PROJ-0001: Project name"}`.

```bash
curl -s -G "https://<your-site>/api/method/card.api.card_project_options" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "company=Example Contracting Co."
```

## report_defaults

`GET /api/method/card.api.report_defaults`

Report filter defaults from Card Settings, for any report role (Card User cannot read Card Settings).

**Permission:** a CARD report role. **Parameters:** none.

**Returns:** `{"default_statement_type": "<value>", "include_draft_in_reports": 0|1}`.

```bash
curl -s "https://<your-site>/api/method/card.api.report_defaults" -H "Authorization: token <api_key>:<api_secret>"
```

## download_pdf

`POST /api/method/card.card.report.equipment_supplier_statement.statement_pdf.download_pdf`

Runs the **Equipment Supplier Statement** with the caller's permissions and returns the A4 statement as a PDF rendered
by the Chrome PDF generator (correct Arabic shaping). The endpoint accepts filters only, never HTML.

**Permission:** the report's roles, **print** on Card Monthly Card, and the standard report and filter-value checks;
the company is validated by the report.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `filters` | object | Yes | The report filters: `company`, `statement_type`, `supplier`, `from_month`, `from_year`, `to_month`, `to_year`, `project`, `equipment`, `equipment_type`, `include_draft`. Plain values only; a list or object value is refused. |

**Returns:** the PDF file (`Equipment Supplier Statement.pdf`, translated). **Side effects:** writes an Access Log
entry.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.report.equipment_supplier_statement.statement_pdf.download_pdf" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"filters": {"company": "Example Contracting Co.", "statement_type": "مورد", "supplier": "Supplier A", "from_month": "01", "from_year": 2026, "to_month": "01", "to_year": 2026}}' \
  -o statement.pdf
```

## Related

- [Suppliers and customers](/card/features/suppliers-customers/)
- [Parties and statements reports](/card/reports/parties-statements/)
- [Print formats](/card/features/print-formats/)
