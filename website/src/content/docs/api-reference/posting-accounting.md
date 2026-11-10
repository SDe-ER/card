---
title: Posting and Accounting API
description: Endpoints for the monthly posting screen, building and rebuilding draft invoices, accepting corrections, and linking hand-booked invoices and accrual journal entries.
sidebar:
  order: 8
---

## Overview

CARD never writes ledger entries. Its monthly posting builds **one draft ERPNext invoice per party and month** — a
Purchase Invoice for a supplier, a Sales Invoice for a customer — from the party's unposted submitted sources (monthly
cards, diesel fills, transports), and records the link in a **GL Posting Log**. The ledger rows appear only when a
person submits the invoice in ERPNext. When a source was already paid by a hand-booked invoice or recognised by an
accrual journal entry, an accountant links it instead, so CARD never builds it twice.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `card.gl.posting.posting_month_parties` | Parties of a company-month with their posting status. |
| GET | `card.gl.posting.preview_month` | Dry run of the next build of a party-month. |
| POST | `card.gl.posting.post_month` | Build the draft posting of a party-month. |
| POST | `card.gl.posting.rebuild_month` | Delete the CARD draft and build the month again. |
| POST | `card.gl.integrity.accept_correction` | Accept a cost center / account correction on a CARD draft. |
| POST | `card.gl.integrity.link_supplier_invoice` | Link a hand-booked Purchase Invoice to CARD sources. |
| POST | `card.gl.journal_link.link_accrual_journal` | Link a supplier accrual Journal Entry to CARD cards. |

## Common rules for the posting endpoints

`posting_month_parties`, `preview_month`, `post_month` and `rebuild_month` share one gate:

- Role **Card Manager** or **System Manager**.
- The company must be one the user may see for Card Monthly Card, Project Diesel Fill, Equipment Transport, the invoice
  DocType of the side and GL Posting Log.
- `party_type` is `Supplier` or `Customer`; `month` is 1–12 and `year` a number.
- For a single party, the user must be able to read the party (User Permissions on Supplier or Customer apply).

## posting_month_parties

`GET /api/method/card.gl.posting.posting_month_parties`

The parties of a company-month: every party with unposted submitted sources or an active CARD posting log. Each side
is listed only when the caller may build that side's postings; parties the caller cannot read are left out.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `company` | string | Yes | Company. |
| `month` | string | Yes | Month number. |
| `year` | string | Yes | Year. |

**Returns:** a list of `{"party_type", "party", "party_name", "pending_sources", "status": "Not posted"|"Draft"|"Posted",
"postings": [{"log", "status", "origin": "Built"|"Linked", "posting_doctype", "posting_doc", "amount"}]}`.

```bash
curl -s -G "https://<your-site>/api/method/card.gl.posting.posting_month_parties" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "company=Example Contracting Co." --data-urlencode "month=01" --data-urlencode "year=2026"
```

## preview_month

`GET /api/method/card.gl.posting.preview_month`

The invoice lines the next post (or rebuild, when a CARD draft exists) would create. Nothing is inserted, saved,
reserved or logged.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `company` | string | Yes | Company. |
| `party_type` | string | Yes | `Supplier` or `Customer`. |
| `party` | string | Yes | Supplier or Customer. |
| `month`, `year` | string | Yes | Period. |

**Returns:** an object with `company`, `party_type`, `party`, `party_name`, `month`, `year`, `posting_doctype`, `mode`
(`post` or `rebuild`), `replaces` (drafts a rebuild deletes), `currency`, `posting_date`, `sequence`, `lines`,
`discount`, `net_total`, `taxable_net`, `zero_rated_net`, `vat_registered`, `tax_template`, `vat_rate`, `vat_estimate`
(an estimate: ERPNext computes the taxes), `diesel_note`, `sources` (`doctype`, `name`, `amount`), `review_invoices`
(supplier invoices an accountant must review first, readable ones only), `hidden_review_invoices`, `can_review`,
`warnings`, and `blocked` — the builder's own message when the build would be refused.

```bash
curl -s -G "https://<your-site>/api/method/card.gl.posting.preview_month" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "company=Example Contracting Co." --data-urlencode "party_type=Supplier" \
  --data-urlencode "party=Supplier A" --data-urlencode "month=01" --data-urlencode "year=2026"
```

## post_month

`POST /api/method/card.gl.posting.post_month`

Creates **one draft** posting (Purchase Invoice for a supplier, Sales Invoice for a customer) for the party's unposted
submitted sources of that month.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `company`, `party_type`, `party`, `month`, `year` | string | Yes | As above. |
| `reviewed_invoices` | list | No | Supplier invoices of the month an accountant declared unrelated to these sources. |

**Returns:** the draft invoice name. **Side effects:** inserts the draft invoice and its GL Posting Log, reserving the
sources. Refused while existing supplier invoices of the month are not reviewed, or when settings (accounts, tax
template, VAT basis) are missing.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.posting.post_month" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"company": "Example Contracting Co.", "party_type": "Supplier", "party": "Supplier A", "month": "01", "year": "2026"}'
```

## rebuild_month

`POST /api/method/card.gl.posting.rebuild_month`

Late sources against a **draft** posting: deletes the CARD draft (freeing its reservations) and builds the month again,
so the new draft includes every unposted submitted document. Parameters and return value as `post_month`.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.posting.rebuild_month" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"company": "Example Contracting Co.", "party_type": "Customer", "party": "<customer>", "month": "01", "year": "2026"}'
```

## accept_correction

`POST /api/method/card.gl.integrity.accept_correction`

An Accounts Manager accepts a corrected cost center or account on a CARD draft invoice. Only those fields may differ
from what CARD built; the acceptance is tied to the exact invoice content, so any later edit needs a new acceptance.

**Permission:** Accounts Manager or System Manager; write on the invoice; the company within the user's CARD and
accounting scope.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice_doctype` | string | Yes | `Purchase Invoice` or `Sales Invoice`. |
| `invoice` | string | Yes | A CARD-built draft invoice. |
| `reason` | string | Yes | Reason for the correction. |

**Returns:** the GL Posting Log name. **Side effects:** stores the accepted content signature, the accepting user and
the reason on the log.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.integrity.accept_correction" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"invoice_doctype": "Purchase Invoice", "invoice": "<invoice-name>", "reason": "Project cost center corrected"}'
```

## link_supplier_invoice

`POST /api/method/card.gl.integrity.link_supplier_invoice`

Records that an existing supplier Purchase Invoice, booked by hand, already pays for these CARD sources. Nothing is
reposted and the invoice is not changed: a **Linked** GL Posting Log reserves the sources so CARD never builds them
again, and the sources show the invoice once it is submitted. Sources may span several months.

**Permission:** Accounts Manager, Accounts User or System Manager; read and **submit** right on the invoice; read on the
supplier and on every source; the company within the user's CARD and accounting scope.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | string | Yes | Purchase Invoice (not cancelled, not a return, not already a CARD posting or link). |
| `sources` | list | Yes | `[{"doctype": "Card Monthly Card", "name": "..."}]`, where `doctype` is `Card Monthly Card`, `Project Diesel Fill` or `Equipment Transport`; submitted, of the invoice's company and supplier. |
| `reason` | string | With a difference | Why a difference is accepted. |
| `accept_difference` | int | No | `1` to accept a gap between the sources and the invoice net. |

**Evidence rule:** the sources are compared with the invoice's net total on one basis (cards and transports net; fills
by the diesel price VAT basis). A gap, or a basis that cannot be verified, is refused unless accepted with a reason; it
is then stored on the log as an open difference, never shown as matched. An imported diesel session carrying its
supplier invoice number links only to the invoice with that bill number.

**Returns:** the GL Posting Log name.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.integrity.link_supplier_invoice" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"invoice": "<invoice-name>", "sources": [{"doctype": "Card Monthly Card", "name": "<card-name>"}]}'
```

## link_accrual_journal

`POST /api/method/card.gl.journal_link.link_accrual_journal`

Records that a submitted supplier accrual Journal Entry already recognised these submitted supplier monthly cards.
Nothing is posted, created or changed in ERPNext. Cancelling the Journal Entry later frees the cards again.

**Permission:** Accounts Manager, Accounts User or System Manager; read and submit right on the Journal Entry; read on
the supplier and every card; the company within the user's CARD and accounting scope.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `journal_entry` | string | Yes | Submitted ordinary Journal Entry (not opening, debit or credit note) crediting exactly one supplier, with no party row against another document. |
| `cards` | list | Yes | Submitted supplier-side cards of the same company and supplier, not invoiced and not held by another posting; no duplicates. |
| `reason` | string | With a difference | Why a difference is accepted. |
| `accept_difference` | int | No | `1` to accept a gap. |

**Evidence rule:** the supplier credit less the entry's tax rows must equal the cards' net within the reconciliation
tolerance (Card Settings, at least 0.01); a gap is refused unless accepted with a reason and is then stored on the log.

**Returns:** the GL Posting Log name. **Side effects:** inserts a Linked GL Posting Log of type Journal Entry listing
the cards, and marks each card posted.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.journal_link.link_accrual_journal" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"journal_entry": "<journal-entry>", "cards": ["<card-1>", "<card-2>"]}'
```

## Related

- [Invoicing and posting](/card/features/invoicing-posting/)
- [Accounting control reports](/card/reports/accounting-control/)
- [Card Settlement Status](/card/reports/parties-statements/#card-settlement-status)
