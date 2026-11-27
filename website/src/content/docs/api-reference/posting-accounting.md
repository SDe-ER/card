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
| POST | `card.gl.integrity.link_customer_invoice` | Link a hand-booked, submitted Sales Invoice to customer monthly cards. |
| POST | `card.gl.integrity.unlink_customer_invoice` | Remove a wrong link between a Sales Invoice and its monthly cards (System Manager). |
| GET | `card.gl.integrity.unlinked_customer_invoice_candidates` | List the hand-booked Sales Invoices that are not linked, with the cards that can match. |
| GET | `card.gl.integrity.customer_invoice_link_info` | The link state of one Sales Invoice and the cards it could bill (data of the Desk buttons). |
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

## link_customer_invoice

`POST /api/method/card.gl.integrity.link_customer_invoice`

Records that a submitted Sales Invoice, booked by hand in ERPNext, already bills these customer monthly cards. Nothing
is posted and the invoice is not changed: a **Linked** GL Posting Log holds the cards so CARD never builds them again,
and each card shows the invoice. There is no Desk button for this method.

**Permission:** Accounts Manager or System Manager (Accounts User is not enough); read and **submit** right on the
invoice; read on the customer and on every card; the company within the user's CARD and accounting scope.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | string | Yes | Submitted Sales Invoice in the company currency: not cancelled, not a return (credit note), not a debit note, not an opening invoice, without a submitted credit note, and not already a CARD posting or link. |
| `cards` | list | Yes | Card Monthly Card names, for example `["<card-name>"]`. Each card is submitted, not of an open month, billed to a customer, of the invoice's company, customer and project, without a Sales Invoice, and not held by another customer posting. No card twice. |
| `reason` | string | Yes | Why the invoice is linked. It is stored on the log and in the comments. |

**Evidence rule:** the invoice net total (before VAT) must equal the sum of the cards' customer net amounts within the
reconciliation tolerance (Card Settings, at least 0.01), in total and for each project. The project of an invoice line
is the project on the line; a line without a project takes the header project of the invoice. For each project, the
net of its lines must equal the customer net of the listed cards of that project, and no project of the invoice may be
left without cards; an invoice without a project is refused. A difference is always refused; this method has no
`accept_difference`.

**Concurrency:** the invoice row and the card rows are locked, and their status, links and active posting logs are
read again under the locks before the log is inserted.

**Returns:** the GL Posting Log name. **Side effects:** inserts one Linked GL Posting Log of type Sales Invoice with one
source row per card; sets `sales_invoice`, `posted` and `gl_posting` on each card; adds one Info comment on the invoice
and on each card. It writes no GL Entry and does not save the Sales Invoice. A second call for the same invoice is
refused while the link is active. To undo a wrong link, see [unlink_customer_invoice](#unlink_customer_invoice).

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.integrity.link_customer_invoice" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"invoice": "<invoice-name>", "cards": ["<card-name>"], "reason": "Invoice entered in ERPNext before the cards"}'
```

## unlink_customer_invoice

`POST /api/method/card.gl.integrity.unlink_customer_invoice`

Removes a wrong link that `link_customer_invoice` made. It is for a company that cannot cancel a submitted Sales
Invoice (ZATCA). Nothing is posted, cancelled, amended or deleted: the Sales Invoice, the card amounts and the ledger
are not changed. There is no Desk button for this method.

**Permission:** System Manager (Accounts Manager is not enough) and read on the Sales Invoice. The System Manager role
alone does not give read on a Sales Invoice, so the user also needs an accounts role. Also: the company within the
user's CARD and accounting scope, and read on every card of the link.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | string | Yes | Submitted Sales Invoice that is the posting document of an active GL Posting Log with origin **Linked**. |
| `reason` | string | Yes | Why the link is removed. It is stored on the log and in the comments. |

**Refusals:** every check runs before the first write, so a refused call changes nothing.

- The invoice is not submitted, or it has no active link.
- The invoice is a posting that CARD built (origin Built or empty) or a CARD credit note.
- Cancelled-and-amended chain mismatch: another Sales Invoice amends this invoice, or an invoice that this one amends
  (up the chain) still has an active posting log. An amendment that has its own link is unlinked as any other invoice.
- A source of the log is not a monthly card, or the user cannot read a card of the link.
- A card changed after the link: it is not submitted, it is not marked posted, its `sales_invoice` is not this invoice,
  or its `gl_posting` is neither this log nor the active supplier-side log that holds the card (sub-rental). The
  message names the card.

**Concurrency:** the invoice row, the card rows and the log row are locked, in the order of the link (invoice,
cards, posting logs). The invoice status, the log and the link fields of the cards are read under the locks. The amendment chain and the supplier-side
log of a sub-rental card are plain reads.

**Returns:** the GL Posting Log name. **Side effects:** sets the Linked GL Posting Log to `Cancelled` and clears its
`posting_key`; the log is kept, and its `remarks` get who, when, the reason, the invoice, the log and the cards with
their amounts. On each card it clears `sales_invoice`, sets `posted` to 0 (1 stays on a sub-rental card whose supplier
side is still posted by a purchase invoice or a linked accrual Journal Entry) and clears `gl_posting` when it points at this log; the card's `modified` is not changed. It adds
one Info comment on the invoice and on each card. It writes no GL Entry and does not save the Sales Invoice. After the
call, `link_customer_invoice` accepts the invoice and the cards again.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.integrity.unlink_customer_invoice" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"invoice": "<invoice-name>", "reason": "The invoice was linked to the cards of another month"}'
```

## unlinked_customer_invoice_candidates

`GET /api/method/card.gl.integrity.unlinked_customer_invoice_candidates`

Read only. For every customer that has customer-billing cards in the company, lists the submitted Sales Invoices that
CARD did not build and that have no link (no active GL Posting Log), newest first. Returns, debit notes, opening
invoices, invoices with a submitted credit note and invoices in another currency than the company currency are
left out. With each invoice it gives the customer's cards that
can still be linked and that are on a project of the invoice (at most 100 cards; `more_cards` is true when there are
more).

**Permission:** Accounts Manager or System Manager; read on Sales Invoice and on Card Monthly Card; the company within
the user's CARD and accounting scope. Invoices and cards the user cannot read are left out.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `company` | string | Yes | Company. |
| `limit_start` | int | No | First invoice of the page (default 0). |
| `limit_page_length` | int | No | Invoices per call (default 50, at most 200). |

**Match rule:** two sets of cards are tested with the evidence rule of `link_customer_invoice` (the invoice net, in
total and for each project, within the reconciliation tolerance): the cards of the invoice month and the month before,
then all cards that can still be linked on the projects of the invoice. `match` is `exact` when one set covers the
invoice, and `cards` is then that set. No other combination is tested: `none` does not prove that no combination
matches.

**Returns:** `{"invoices": [{"invoice", "posting_date", "customer", "projects": [...], "net_total", "cards": [{"name",
"month", "year", "project", "customer_net_amount"}], "more_cards", "match": "exact"|"none", "note"}], "limit_start",
"limit_page_length", "has_more"}`. **Side effects:** none.

```bash
curl -s -G "https://<your-site>/api/method/card.gl.integrity.unlinked_customer_invoice_candidates" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "company=Example Contracting Co."
```

## customer_invoice_link_info

`GET /api/method/card.gl.integrity.customer_invoice_link_info`

Read only. The data of the Desk buttons **Link to monthly cards** and **Remove link to monthly cards** on the Sales
Invoice form. For one invoice it says whether an active GL Posting Log holds it. If it does, it returns the log, its
origin (`Linked` or `Built`) and its cards. If it does not and the link accepts the invoice (submitted, not a return,
a debit note or an opening invoice, in the company currency, no submitted credit note), it returns the unlinked
approved cards of the customer on the projects of the invoice (at most 100; `more_cards` is true when there are more).

**Permission:** Accounts Manager or System Manager; read on the Sales Invoice and on Card Monthly Card; the company
of the invoice within the user's CARD and accounting scope. The same gates as the candidates list.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `invoice` | string | Yes | Sales Invoice name. |

**Returns:** `{"invoice", "eligible", "linked", "log", "origin", "net_total", "cards": [{"name", "month", "year",
"project", "customer_net_amount"}], "more_cards", "linked_cards": [...]}`. **Side effects:** none.

```bash
curl -s -G "https://<your-site>/api/method/card.gl.integrity.customer_invoice_link_info"   -H "Authorization: token <api_key>:<api_secret>"   --data-urlencode "invoice=<invoice-name>"
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
