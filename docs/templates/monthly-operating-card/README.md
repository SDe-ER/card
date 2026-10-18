# Monthly equipment operating card — D0.6

[Editable HTML](monthly-card.html) · [CSS](card.css) · [Field mapping](field-mapping.csv) ·
[Verification report](verification-report.md)

## Design

Blank Arabic/English monthly equipment operation card, originally designed for Shams Dubai
Contracting Est. (SDCE) and archived on the owner's explicit request. The public template in
this folder ships with a **neutral placeholder identity** (header «اسم المؤسسة / COMPANY
NAME», generic logo alt text, footer form code `FORM-CODE`) — no company is the default.
Front: A4 landscape, days 01–16 on the right and 17–31 on the left, operating hours,
overtime, signatures, notes and monthly totals. Reverse: A4 portrait, 3 equipment-transfer
rows and 13 maintenance/parts/notes rows.

Status: delivered design D0.6; operational approval is not recorded. The owner requested
removal of the printed review label. This does not confer electronic approval.

## Proprietary assets — not distributed here

The SDCE company logo, the branded print-ready PDF and the branded front/back preview images
are **proprietary SDCE assets and are not distributed in this folder**. They remain archived,
unchanged, on the original delivery branch `codex/document-template-library`
(commit `caae620`, PR #64), under
`card/templates/documents/operation-cards/sdce-monthly/d0.6/`.

To use this template, supply your own logo as `company-logo.png` next to `monthly-card.html`
(both the front and the back reference that file name), and set your institution name in the
two header blocks («اسم المؤسسة / COMPANY NAME») and your form code in the two footers
(`FORM-CODE`). The SDCE name and logo belong to SDCE (see the repository's Logo and
Trademark Policy in README.md).

> Dated note (2026-10-18, relocation): three deltas exist against the delivered D0.6 revision
> on the archive branch, all in `monthly-card.html`'s identity and line endings — the form
> layout is unchanged. (1) Logo file reference `shams-dubai-logo.png` → `company-logo.png`
> (2 occurrences). (2) SDCE identity text replaced with neutral placeholders: institution
> header → «اسم المؤسسة / COMPANY NAME» (×2), logo alt → «شعار المؤسسة / Company logo» (×2),
> footer form code `SDCE-CARD-01` → `FORM-CODE` (×2). (3) Line endings normalized CRLF → LF
> by this repository's `.gitattributes` policy (`* text=auto eol=lf`); the delivered files
> were committed through the GitHub API, which bypassed that normalization.
> `manifest.json` is kept verbatim as **archival delivery evidence**: its SHA-256 values
> describe the delivered files exactly as archived on the delivery branch (PR #64, commit
> `caae620`), including the logo, PDF and previews that live only there — they are NOT the
> checksums of the files in this folder. The current files' checksums are recorded in
> [`manifest-current.json`](manifest-current.json).

## Edit and print

Keep `monthly-card.html`, `card.css` and your `company-logo.png` together. Open the HTML in
Chrome/Edge. Print to PDF at 100% with CSS page sizes, no added browser headers or footers,
and background graphics enabled. CSS embeds Cairo Regular/Bold; its SIL OFL license is
included as `Cairo-OFL.txt`. Do not require online font loading.

The output has mixed page orientations (landscape front, portrait reverse). Check one duplex
sheet for driver rotation before batch printing; do not assume a universal
long-edge/short-edge setting. Physical print testing has not been performed. After source
edits, regenerate the PDF and previews and repeat pagination, font embedding, 31-day, RTL and
overflow checks.

## Data mapping and limits

See `field-mapping.csv` and `verification-report.md`. Source inspection baseline was
SDe-ER/card commit `d69fa67038b1fe7f448cf1109fda30552120091e`; mapping is historical source
evidence, not a claim that current production or newer repository revisions match.

Regular and overtime hours are mutually exclusive on paper. Office entry combines them once
in `working_hours` (8 + 2 = 10). No overtime field or premium rate is implied. Daily
signatures, maintenance parts and detailed project-transfer evidence are paper data, not
newly created CARD fields. No transaction, settings or schema changes occur.

## Scope

This folder archives a standalone print design only. It is not a Frappe Print Format fixture
and is not automatically available in Desk, installed, migrated or deployed. Runtime
integration requires a separate explicit implementation and review.

`manifest.json` records SHA-256 checksums of the complete delivered D0.6 package. The
exported CSS is excluded from automatic Prettier rewriting (see `.prettierignore`) to
preserve this validated snapshot; a new design revision should be regenerated and validated
as a complete package.
