# Document template instructions

Owner instruction: every new or revised printable design must be stored in this
repository's template library, including invoices, receipts, account statements,
diesel reports and equipment-operation cards.

1. Use `card/templates/documents/<category>/<design>/<revision>/` for document designs.
2. Categories: `operation-cards`, `invoices`, `receipts`, `account-statements`,
   `diesel-reports`, `other`. Add a category when needed and update the catalog.
3. Deliver editable HTML/CSS or the native editable source, required images/fonts and
   their notices, a PDF, front/back or page previews, a README and validation notes.
4. Register every delivered revision in `documents/README.md`; identify the current
   revision and preserve older delivered revisions instead of silently overwriting them.
5. Document intended paper size, orientation, print scale, required assets and field
   mapping/gaps. Do not invent CARD fields, approvals, calculations or posting behavior.
6. Upload the complete design package through the repository's normal branch/PR process
   when authorized. Never bypass protected branches or silently deploy a template.
7. Use blank forms or synthetic examples only. Owner-authorized company branding may
   stay in its specific design folder; do not spread it into shared application code.
8. Do not move existing runtime templates, `pages/`, DocTypes, reports or fixtures just
   to satisfy this library layout. Runtime integration is a separate reviewed change.
9. A template's review status is separate from CARD's electronic document status.
   Removing a printed draft label does not grant operational approval.
