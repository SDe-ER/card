# CARD document template library

This library is the required repository home for all new or revised **printable designs**:
operation cards, invoices, receipts, account statements, diesel reports and other documents.
It is a design archive, not an automatically installed ERPNext Print Format collection.

Document designs live **here under `docs/templates/`, never inside the installable `card/`
Python package**: design sources, PDFs and images must not ship in the application wheel
unless a confirmed runtime need exists. Existing `pages/`, Python files, runtime Jinja
templates and Print Format fixtures are application infrastructure; this library does not
replace, relocate, register, install or deploy any of them.

## Catalog

| Category | Design | Current revision | Status |
| --- | --- | --- | --- |
| Operation cards | [Monthly equipment operating card](monthly-operating-card/README.md) | D0.6 | Owner-requested design; operational approval not recorded |
| Invoices | No design uploaded yet | — | Reserved category |
| Receipts | No design uploaded yet | — | Reserved category |
| Account statements | No design uploaded yet | — | Reserved category |
| Diesel reports | No design uploaded yet | — | Reserved category |
| Other documents | No design uploaded yet | — | Reserved category |

Reserved categories get their folder with their first design. Only the latest delivered
operation-card design is imported here; earlier iterations remain in the originating work
session and are not represented as uploaded revisions.

## Rules for adding a design

1. Use `docs/templates/<design>/` (one folder per design; add a revision subfolder when an
   older delivered revision must be preserved alongside a newer one — never silently
   overwrite a delivered revision).
2. Deliver editable HTML/CSS or the native editable source, required font notices, a README
   and validation notes; register the design in the catalog table above.
3. Document intended paper size, orientation, print scale, required assets and field
   mapping/gaps. Do not invent CARD fields, approvals, calculations or posting behavior.
4. **Company-specific branding (logos, branded renders) is separated from the public,
   distributable files**: reference a placeholder asset (e.g. `company-logo.png`) from the
   sources and keep proprietary assets out of the distributed tree. Never spread branding
   into shared application code.
5. Use blank forms or synthetic examples only — no real transactions, personal data or
   financial records.
6. Upload the complete design package through the repository's normal branch/PR process when
   authorized. Never bypass protected branches or silently deploy a template.
7. A template's review status is separate from CARD's electronic document status. Removing a
   printed draft label does not grant operational approval.
