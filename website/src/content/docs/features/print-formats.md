---
title: Print Formats
description: Every print format CARD ships — monthly card, transport, diesel fill, tool handover receipt and the A4 supplier statement — with their content, language, direction and letter head.
sidebar:
  order: 20
---

## Overview

CARD ships its own print formats for the documents people sign or send: the monthly operation card, the equipment
transport, the diesel fill, the tool handover receipt and the A4 supplier statement. All of them follow the standard
Frappe print style — a white page with the Frappe print greys, the company name above the title, the details as a
label and value grid, a rows table, a totals table at the end side of the page and signature lines at the bottom.

Every print follows the **print language**: its fixed texts are translated, and the page is right to left for
Arabic and other right-to-left languages, left to right otherwise.

<!-- screenshot: print-formats-monthly-card -->

## Key concepts

| Concept | Meaning |
|---|---|
| **Standard print format** | A print format shipped as a file of the app (module Card); updated by every migrate. |
| **Default print format** | The format used by the Print button unless the user picks another. Set by the installer for the three CARD transactions. |
| **Print language** | The language chosen in the print dialog (or the user's language). It decides the texts and the page direction. |
| **Letter Head** | The standard ERPNext letter head with the company logo and details. |
| **Report print format** | A print format attached to a report, used by the report's Print and PDF actions. |

## Features

### Formats at a glance

| Print format | For | Default |
|---|---|---|
| **Card Monthly Card Print** | Card Monthly Card | Yes |
| «كارت تشغيل شهري» (legacy) | Card Monthly Card | Kept where it already was the default |
| **Equipment Transport Print** | Equipment Transport | Yes |
| **Project Diesel Fill Print** | Project Diesel Fill | Yes |
| **Tool Handover Receipt** | Employee Tool Custody | — |
| **Equipment Supplier Statement A4** | Equipment Supplier Statement report | Report print (A4 portrait) |

Draft documents print with *(Draft)* after the title and cancelled documents with *(Cancelled)*.

### Card Monthly Card Print

The monthly operation card of one machine, shift and month.

- **Header** — the selected Letter Head, the company name and the title *Equipment Monthly Operation Card*.
- **Details** — card no., month, shift type, equipment name and code, equipment type, ownership and card direction,
  project name, location, driver / operator, the owner (supplier, or the company for an owned machine) or the
  customer, and the period. The equipment image prints beside the details when set.
- **Days grid** — the days of the month in two side-by-side halves: #, date, day (printed from the date in the print
  language), status, hours, idle reason and notes. Fridays and non-working days are shaded.
- **Additions and deductions** — side (supplier or customer), type, description and amount, when the card has any.
- **Card totals** — total operating hours, working days, the rate with its basis and the total amount; for a card
  with a customer side also the customer rate and amount. A card with neither side prints *Internal operation — Not
  billed*.
- **Settlement** — for each billed side, a *Supplier settlement* or *Customer settlement* table: gross, additions,
  deductions and *net before VAT*. The net equals the amount CARD puts on that side's invoice line before VAT.
- **Signatures** — driver / operator (with his name), site supervisor approval, project manager approval.

The legacy Arabic format «كارت تشغيل شهري» ships as a fixture and stays available as an alternative with the same
style and the same print-language behaviour.

### Equipment Transport Print

- Document no., date, project, transport supplier, from (source project or place), to (destination project or
  place), transport method and remarks.
- A row per machine moved, with its **cost share**.
- **Amount summary** with the transport amount, and the **amount in words** in the company currency.
- Signatures: *Prepared By*, *Received By*, *Approved By*.

### Project Diesel Fill Print

- Document no., date, project, supplier, the equipment (when the fill is for one machine) and remarks.
- **Amount summary**: litres, unit price and amount, and the amount in words.
- Signatures: *Prepared By*, *Received By*, *Approved By*.

### Tool Handover Receipt

For an **Employee Tool Custody** movement (Handover, Return, Transfer, Loss or Damage).

- Title with the movement type; document no. and date.
- The employee, and the receiving employee (Transfer) or the warehouse; the equipment and the project; notes.
- The tool: item, quantity and serial number.
- The statement *The receiver confirms receiving the tool above in good condition and is responsible for it until
  it is returned or handed over.*
- Two signatures, *Handed over by* and *Received by*, with the names of the giver and the taker of that movement
  (for a Return the worker gives and the store receives).

### Equipment Supplier Statement A4

The print and PDF of the [Equipment Supplier Statement](/card/reports/parties-statements/) report, on one A4
portrait page for a normal period.

- **Header** — company, title *Equipment Supplier Statement*, statement type (Supplier or Owned equipment),
  supplier, issue date, and the period as full dates (first day of the start month to the last day of the end
  month). *Includes draft cards* is printed when the report includes drafts.
- **Rows** — every row of the period: projects, equipment and every card (labelled with its shift), then the grand
  total. Columns for a supplier statement: label, first date, last date, working days, hours, hourly rate, amount,
  additions, deductions and net. For owned equipment: label, first and last date, working days and hours.
- **Dynamic columns** — additions and deductions print only when a row has a value, and billable stopped hours print
  after the hours only when a row has them; the other columns share the freed width.
- **Statement totals** — placed under the amount columns: *Cards net for the period* and, when positive, *Work done
  not yet invoiced (before VAT)*. For owned equipment: equipment, days and hours.
- **Signatures** — accountant and reviewer, plus supplier on a money statement; and the line *Issued by the
  electronic system of \<company\>*.

The report's **PDF** action sends only the filters to the server, which runs the report with the user's permissions
and renders the page with the Chrome PDF generator so Arabic letters join correctly. The statement uses the Noto
Sans Arabic font and keeps it even when a site print style sets another font. Each PDF download is recorded in the
Access Log.

### Language and direction

- Fixed texts are translated into the print language.
- The page is right to left for Arabic, Hebrew, Persian and Pashto, and — in CARD — Urdu.
- Values stored in Arabic (ownership, shift, day status, rate basis, direction, adjustment type) print translated
  through CARD's translation files; names in the data print as stored.
- Numbers read left to right and are right-aligned; dates and counts are centred.
- **Amount in words** uses the company currency. In Arabic, when the currency code has no Arabic translation, the
  currency symbol replaces the code.

See [Languages](/card/features/languages/).

### Letter head and fonts

- At install, when the site has **no** Letter Head at all, CARD creates a Letter Head named **CARD** from the default
  company (name, tax ID, phone, logo). An existing Letter Head is never changed.
- The monthly card print places the selected Letter Head at the top; the transport, diesel fill and tool handover
  prints start with the company name.
- The four document formats render their PDF with the Chrome PDF generator.
- CARD bundles the Noto Sans and Noto Sans Arabic fonts and installs them for the bench user on every migrate, so the
  server PDF shapes Arabic correctly. If that fails, the PDF falls back to the system font.

## Permissions

| Action | Who |
|---|---|
| Print a document | Users with print rights on the document (its DocType permissions and company) |
| Print or download the supplier statement PDF | Users who may run the report and print Card Monthly Card, for a permitted company |
| Change the default print format | System Manager (Customize Form) |

## Related

- [Monthly cards](/card/features/monthly-cards/)
- [Transport](/card/features/transport/)
- [Diesel](/card/features/diesel/)
- [Tool custody](/card/features/tool-custody/)
- [Parties & statements reports](/card/reports/parties-statements/)
- [Languages](/card/features/languages/)
