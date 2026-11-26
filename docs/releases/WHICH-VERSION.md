# Which Version Should I Use?

The latest release is not automatically the right one for every site. Pick by compatibility and
need; every claim below is backed by the per-version pages (evidence links there).

## Quick answer

| Your situation | Use | Why |
|---|---|---|
| Site on v4.10.x, v4.11.x or v4.12.x | **v4.13.0** | Everything in v4.12.2, plus: a Monthly Card is approved only after its month ends and a card of an open month can be reopened on its own number (FR-191), the maintenance payer on the equipment (FR-192), and the report Project Invoice Profitability (FR-193). Read the behaviour change first: an approval before the month end is refused for every role. One patch, one new column; rollback is code only |
| Site that must keep approving Monthly Cards before the month ends (superseded by v4.13.0 otherwise) | **v4.12.2** | Everything in v4.12.1, and the PDF of the Equipment Customer Statement joins Arabic letters correctly (issue 324). Backward compatible; no patch and no database change; rollback is code only |
| Site on v4.10.x, v4.11.x or v4.12.0 (superseded by v4.12.2: its customer statement PDF breaks Arabic joins) | **v4.12.1** | Everything in v4.12.0, and the Company settings row editor of Card Settings opens, so the company settings can be changed in the Desk form (issue 320). Backward compatible; no patch and no database change; rollback is code only |
| Site on v4.10.x or v4.11.x (superseded by v4.12.1: its Company settings row editor does not open) | **v4.12.0** | Everything in v4.11.1 (the upgrade adds no accounting dimension unless Card Settings switches it on), plus three optional company settings that are off by default (FR-188, FR-189, FR-190). Backward compatible; no patch of its own; rollback is code only |
| Site on v4.10.x or v4.11.0 that wants only the fixes and checks, without the new settings | **v4.11.1** | Everything in v4.11.0, and the upgrade adds **no** accounting dimension unless Card Settings switches it on (FR-180). FR-173 additions and deductions without an Adjustment type; FR-178, FR-179, FR-181 card money level in seven reports; FR-187 A4 customer statement; FR-184 hour settings only from Card Settings; FR-177 period runs notice loads. Backward compatible; three patches (Card Settings values only); rollback is code only |
| Site on v4.10.1 or v4.10.0 that wants the accounting dimension created by the upgrade itself | **v4.11.0** | FR-175 date-range supplier statement; FR-176 payments by equipment (the upgrade adds the Card Equipment accounting dimension: empty columns on the accounting tables); FR-174 print totals. Backward compatible; rollback to v4.10.1 is code only |
| Site on v4.10.0 that needs only the FR-172 fixes | **v4.10.1** | FR-172: the Adjustment date column shows for users who saved their own grid columns; the form shows the customer-side net live. Backward compatible; one display-settings patch; rollback to v4.10.0 is code only |
| Site on v4.9.0 that needs dated additions and deductions or owner-paid cash payments, **and** whose API clients and Data Import templates send `adjustment_date` (read the v4.10.0 breaking changes first) | **v4.10.0**, or **v4.11.0** (same capability plus the FR-172, FR-174 and FR-175 changes) | FR-168, FR-169, FR-170, FR-171. Not backward-compatible for writers of adjustment rows. Cash posting stays OFF until separately enabled. Rollback to v4.9.0 is code only (v4.10.0 page, section 12) |
| Site that bills customer equipment per load or per m³, or needs unapproved cards marked on paper (read the v4.8.0 breaking changes first, they apply to a site on v4.7.0) | **v4.9.0** | FR-166 (per-m³ billing) and FR-167 (review copy print), plus everything in v4.8.0. Rollback to v4.7.0 is code only; drafts with the per-m³ rate type must be changed first (v4.9.0 page, section 12) |
| Site on v4.7.0, v4.6.0, v4.5.0 or v4.4.3 (or earlier, see below) that wants: approval delegation, approval tiers, native approval workflows, money privacy on Card Monthly Card, Diesel Dispense → draft Stock Entry, the diesel variance report, the daily log mobile screens, the documentation site, or the governance and privacy hardening of v4.8.0 | **v4.8.0** | Everything in v4.7.0 plus the v4.8.0 changes listed in the [one-line summary](VERSION-HISTORY.md) and the per-FR entries in the [CHANGELOG `[4.8.0]` section](../../CHANGELOG.md#480--2026-11-14). Multiple idempotent patches; a few new submittable DocTypes; every new rule is opt-in per company or warn-only — current behaviour is the default on every site. The party portal is scaffold only (404 until a later wave adds the routes + owner grants portal reads). See [v4.8.0.md → Installation & Upgrade](v4.8.0.md#12-installation--upgrade--partially-verified) |
| Site on v4.6.0, v4.5.0 or v4.4.3 (or earlier, see below), especially one with company-restricted CARD users | v4.7.0 | Everything in v4.6.0 plus the company checks on tool custody, equipment needs requests and reviews (security), the VAT rate from the company's tax templates, the diesel-fill equipment status guard (Warn only) and the Equipment Location History report. No patch, no schema change; the read-only FR-127 tax template check must pass before the deploy ([v4.7.0.md → Installation & Upgrade](v4.7.0.md#12-installation--upgrade--partially-verified)) |
| Site on v4.5.0 or v4.4.3 (or earlier, see below) that needs stop reasons, dated diesel prices, the per-company equipment and diesel guards, the posting preview, the analytics reports or the security fixes of the wave-2 train | **v4.6.0** | Everything in v4.5.0 plus the changes of [v4.6.0.md](v4.6.0.md). Three idempotent data patches, two new DocTypes and new columns; new rules are warn-only or off by default, but some changes apply by default (GET-only reads, stricter attachments, mandatory cancel reason, reviewer not approver, owned-only units, `diesel_unit_price` read-only once scheduled; see [section 9](v4.6.0.md#9-breaking-changes--verified)). Setup actions and rollback plan: [v4.6.0.md → Installation & Upgrade](v4.6.0.md#12-installation--upgrade--partially-verified) |
| Site on v4.4.3 (or earlier, see below) whose supplier cards were recognised by hand with accrual journal entries, or that needs paid/remaining per card | **v4.5.0** | Everything in v4.4.3 plus the accrual journal link (accountant-only, POST) and the read-only Card Settlement Status report. No patch, no schema change; migrate adds the report and its sidebar link; restart the workers ([v4.5.0.md → Installation & Upgrade](v4.5.0.md#12-installation--upgrade--partially-verified)) |
| Site on v4.4.2 (or earlier, see below) that downloads the supplier statement as PDF in Arabic, or whose site print style sets every print font | **v4.4.3** | Everything in v4.4.2 plus the statement PDF rendered with the Chrome PDF generator (Arabic letters join) on one A4 portrait page, and the statement font kept under a site print style. No patch, no schema change; migrate re-imports only the A4 print format; restart the workers; the site's Chrome PDF generator must work ([v4.4.3.md → Installation & Upgrade](v4.4.3.md#12-installation--upgrade--partially-verified)) |
| Site on v4.4.1 (or earlier, see below) that prints the A4 supplier statement for suppliers, including suppliers with cards not yet invoiced | **v4.4.2** | Everything in v4.4.1 plus the statement print listing every card of the period and totals from the cards only (cards net; work done not yet invoiced through CARD, before VAT, when positive), the issued-by footer and full From/To dates. No patch, no schema change; migrate re-imports only the A4 print format; restart the workers. The print no longer shows the ledger balance (use the screen report or the ERPNext ledger). The PDF button still uses wkhtmltopdf; use browser Print ([v4.4.2.md → Installation & Upgrade](v4.4.2.md#12-installation--upgrade--partially-verified)) |
| Site on v4.4.0, or on v4.3.0, that prints CARD documents to PDF in Arabic, or that needs the printed ledger balance (opening + period charges − payments = closing) on the supplier statement | **v4.4.1** | Everything in v4.4.0 plus the Chrome PDF generator for the CARD document prints (wkhtmltopdf broke Arabic letter joining) and the short totals on the A4 supplier statement. No patch, no schema change; migrate re-syncs the print formats; the site's Chrome PDF generator must work (print each CARD format once after the deploy). The supplier statement PDF button still uses wkhtmltopdf; use browser Print ([v4.4.1.md → Installation & Upgrade](v4.4.1.md#12-installation--upgrade--partially-verified)) |
| Site on v4.3.0 that prints CARD documents or the supplier statement and cannot use the Chrome PDF generator | **v4.4.0** | Everything in v4.3.0 plus the standard print style for all CARD prints, prints in the user's language and direction, and the cleaner A4 supplier statement. No patch, no schema change; migrate re-syncs the print formats; restart the workers. A code-only rollback needs a forced re-import of the old formats ([v4.4.0.md → Installation & Upgrade](v4.4.0.md#12-installation--upgrade--partially-verified)) |
| Site on ERPNext **v16.54.0 or later** (Company Restriction), or about to update ERPNext to it | **v4.3.0** or later | The first CARD version compatible with the ERPNext v16.54.0+ portal catalog / Company Restriction: on earlier CARD versions the Card portal roles (Card Operator, CARD Mobile catalog) get an empty catalog. Sites updating ERPNext to ≥ 16.54.0 need 4.3.0. Shown by CI only (Partially Verified). Read the breaking changes first |
| Site that posts CARD months to ERPNext and needs posting integrity, project cost centers and transport cost responsibility | **v4.3.0** or later | Everything in v4.2.2 plus signed posting drafts, hand-booked invoice review, the diesel VAT basis, project/assignment cost centers, transport responsibility with a financial decision, four read-only review reports, Card Equipment financial privacy and the night-shift customer rate. Needs a migrate (new columns, no patch) and data checks before the first build: diesel VAT basis per company, project and assignment cost centers, rebuilt drafts, a responsibility on every draft transport. External clients that write Equipment Transport must send `responsibility` ([v4.3.0.md → Breaking Changes](v4.3.0.md#9-breaking-changes--verified)) |
| Site that records project diesel fills with meter photos and an operations review, and cannot yet do the v4.3.0 data checks | **v4.2.2** | The large meter photos and clearer reading labels on top of v4.2.1 (simpler diesel fill form) and v4.2.0, which has all of v4.1.2 plus the diesel session evidence (opening/closing meter photos, readings, totalizer check, operations approval before submit), the WhatsApp session import as drafts, parts fitment in the catalog and the app name CARD in every language. Needs a migrate (new columns and one child table) |
| Site on v1.0.1 – v4.0.0 going live with equipment registration, transport and project assignment | **v4.1.2** or **v4.2.0** | All of v4.1.1 plus the full launcher navigation on upgraded sites, the simpler transport form and English for stored Arabic values; v4.1.1 added the Tool Custody item-search fix (Card Manager no longer needs an ERPNext Item permission to use the New Handover dialog). Upgrade from v1.0.1 rehearsed; unique chassis/plate numbers; isolation and concurrency fixes |
| Site on v3.0.0 that wants operators to request machine parts/tools and management to approve them into ERPNext Material Requests | **v4.0.0** | Equipment needs, supervisor review, approval into draft Material Requests, tool custody; everything from v3.0.0. Needs companion ERPNext roles for approvers/supervisors |
| New install on frappe **16.51+**, equipment moves recorded as transports | **v3.0.0** | Launcher, transport-driven cards, Asset-linked equipment; everything from v1.2.2 |
| New install, Frappe/ERPNext **v16.5x**, transports not recorded | **v1.2.2** | v3.0.0 refuses a monthly card without an approved transport for the month |
| **Multi-company** site (any) | **v1.2.2 or v3.0.0** | v1.2.0/v1.2.1 registries expose party-wide totals across companies (#23, fixed in v1.2.2) |
| Site with operational (non-accounting) users running filtered reports | **v1.2.1 or later** (prefer v1.2.2) | Before v1.2.1 a Card User could not filter reports by supplier/customer/project (#21) |
| Frappe v16 **below 16.50** (e.g. 16.33–16.4x) | **v1.0.1** | Last version validated on pre-16.50 minors; v1.2.x is tested on 16.5x only (earlier minors: Unknown) |
| Only the original supplier monthly-card workflow, no accounting/customers/diesel | **v1.0.1** (pre-16.50) or **v1.2.2 with accounting off** (16.5x) | v1.2.2 keeps accounting off by default; the classic workflow is unchanged |
| Must match what is verified deployed on SDCE production (as of 2026-10-18) | **v1.0.1** | The only version with a verified production deployment (2026-10-13). v1.2.x is published, not deployed |

## Never use

- **v1.0.0** on Frappe ≥ 16.51 — `bench migrate` fails (fixed in v1.0.1).
- **v1.2.0 / v1.2.1** on multi-company sites — registry totals are not company-isolated (#23).
- Any version number that has no tag + GitHub Release on SDe-ER/card — it is not a CARD release
  (see [VERSION-HISTORY.md](VERSION-HISTORY.md)).

## Upgrade path

- `v1.0.1 → v4.1.0` directly: all pending patches run once (21); rehearsed with synthetic data (CHANGELOG 4.1.0 → Migration). Rehearse on a restored copy of production before deploying.
- `v3.0.0 → v4.0.0`: one `v4_0_0` patch (roles) runs once, idempotently; then set the stores in Card
  Settings → Materials, create the Card Equipment dimension if missing, and give the roles
  ([v4.0.0.md → Installation & Upgrade](v4.0.0.md#12-installation--upgrade--partially-verified)).
- `v1.2.2 → v3.0.0`: two `v3_0_0` patches run once, idempotently; before the first v3 month, record
  a transport for every working machine and map Asset categories to equipment types
  ([v3.0.0.md → Installation & Upgrade](v3.0.0.md#12-installation--upgrade--partially-verified)).
- `v1.0.x → v1.2.2` directly: supported and tested; all `v1_2`, `v1_2_1`, `v1_2_2` patches run once,
  idempotently ([v1.2.2.md → Installation & Upgrade](v1.2.2.md#12-installation--upgrade--verified)).
- Always rehearse `bench migrate` on a restored copy of production first; a migrate that fails on
  the copy must never be run on production (README → Upgrading).
- `v4.2.2 → v4.3.0`: no patch; migrate syncs new columns and field levels. Do the checks in
  [v4.3.0.md → Installation & Upgrade](v4.3.0.md#12-installation--upgrade--partially-verified) before the first
  build. v4.2.2 code is not proven safe on data created under 4.3.0; rollback = restore the pre-upgrade backup or
  fix forward.
- `v4.3.0 → v4.4.0`: no patch, no schema change; migrate re-imports the five standard print formats and the
  print format fixture; restart the workers. Rollback to v4.3.0: the old code runs on the data, but the old
  print formats must be re-imported with `force` (a plain migrate keeps the newer rows)
  ([v4.4.0.md → Installation & Upgrade](v4.4.0.md#12-installation--upgrade--partially-verified)).
- `v4.4.0 → v4.4.1`: no patch, no schema change; migrate re-imports the five standard print formats and the
  print format fixture; restart the workers; print each CARD document format once (Chrome PDF generator).
  Rollback to v4.4.0: the old code runs on the data (the extra summary `key` is unused), but the v4.4.0 print
  formats must be re-imported with `force`
  ([v4.4.1.md → Installation & Upgrade](v4.4.1.md#12-installation--upgrade--partially-verified)).
- `v4.4.1 → v4.4.2`: no patch, no schema change; migrate re-imports only the `Equipment Supplier Statement A4`
  print format; restart the workers. Rollback to v4.4.1: the old code runs on the data, but the v4.4.1 A4 format
  must be re-imported with `force`
  ([v4.4.2.md → Installation & Upgrade](v4.4.2.md#12-installation--upgrade--partially-verified)).
- `v4.4.2 → v4.4.3`: no patch, no schema change; migrate re-imports only the `Equipment Supplier Statement A4`
  print format; restart the workers. Rollback to v4.4.2: the old code runs on the data, but the v4.4.2 A4 format
  must be re-imported with `force`
  ([v4.4.3.md → Installation & Upgrade](v4.4.3.md#12-installation--upgrade--partially-verified)).
- `v4.4.3 → v4.5.0`: no patch, no schema change; migrate adds the Card Settlement Status report and its sidebar link;
  restart the workers. Rollback to v4.4.3: the old code ignores Journal Entry links, so linked cards count as not
  invoiced again; keep accounting disabled or cancel the links first
  ([v4.5.0.md → Installation & Upgrade](v4.5.0.md#12-installation--upgrade--partially-verified)).
- `v4.5.0 → v4.6.0` (and `v4.4.3 → v4.6.0`): three idempotent patches (`v4_6_0.derive_unit_component_flag`,
  `v4_6_0.seed_stop_reasons`, `v4_7_0.seed_diesel_price_schedule`), two new DocTypes and new columns; restart the
  workers. Rollback to v4.4.3: the old code runs on the data but the columns, tables, seeded rows and derived flags
  stay; amend other-party transports, handle move-day transports and set `diesel_unit_price` to the current price
  first ([v4.6.0.md → Rollback plan](v4.6.0.md#126-rollback-plan)).
- `v4.6.0 → v4.7.0`: no patch, no schema change; restart the workers; run the read-only FR-127 tax template
  check first. Rollback to v4.6.0 (`87c375d`) is code only but re-opens the cross-company gaps fixed by FR-129
  ([v4.7.0.md → Rollback plan](v4.7.0.md#126-rollback-plan)).
- Downgrades are not supported by patches; rollback = restore the pre-upgrade backup.

## Things the latest version still does not do (so you don't choose it for the wrong reason)

- No automatic matching of external ERPNext invoices to cards — "invoices outside Card" are listed
  for **manual** reconciliation only (v1.2.2).
- Diesel **cost** totals mix recorded and estimated amounts (litres are split; #33 partially fixed).
- Full-day billing for the per-day rate basis is **Planned** (Unreleased), not available: the
  per-day basis bills hours-prorated.
- Broader accounting phases (activation workflow, tax classes, claims, allocation shares) are an
  approved design, not shipped.
- Transport customer invoicing, supplier recovery documents and Purchase Invoice posting of transports recorded
  with a responsibility are disabled in v4.3.0, v4.4.0, v4.4.1, v4.4.2 and v4.4.3: the accountant enters the transporter's invoice.
