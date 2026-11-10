# CARD — Version Comparison Matrix

Feature-by-feature comparison of every published release. **Status values:** ✅ supported ·
⚠️ supported with the noted caveat · ❌ not present · labels **Verified / Partially Verified /
Unknown / Not Supported / Deprecated / Removed** per the
[release policy](RELEASE-POLICY.md). Evidence column: CHANGELOG section, PR/issue, or file path at
the tag (`git show <tag>:<path>`).

| Feature | First in | v1.0.0 | v1.0.1 | v1.2.0 | v1.2.1 | v1.2.2 | v3.0.0 | v4.0.0 | v4.1.0 | Behaviour changes / notes | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Equipment master (type, category, ownership, supplier, company) | v1.0.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ Asset-linked equipment: name/brand/type from the Asset (read-only) | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | v1.2.2: commercial terms + control fields write-protected (Card Manager), change reason required; v4.3.0: financial fields at levels 1/2, night-shift customer rate | CHANGELOG 1.0.0 / 1.2.2 Security; `card/card/doctype/card_equipment` |
| Project assignments + overlap prevention | v1.0.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ written by transports; required for monthly cards | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | v1.2.2: Card Manager-only writes, validated dates/company; unit days checked against unit's own assignments | CHANGELOG 1.2.2 |
| Monthly operation card (day grid, totals, net) | v1.0.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ project from approved transports; refused without one | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | v1.2.0: hours-only entry, direction-aware; rates snapshot | CHANGELOG 1.0.0 / 1.2.0 |
| Supplier registry + 2 supplier reports (GL reconciliation) | v1.0.0 | ✅ | ✅ | ✅ | ⚠️ sided totals fixed | ⚠️ stored totals **Removed** → per-company figures; reconciliation in 3 figures | ✅ | ✅ | ✅ | — | #24/PR #27; #23; CHANGELOG 1.2.2 Fixed |
| Card workspace + desktop icon | v1.0.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + CARD launcher (Dock) | ✅ | ✅ | v1.0.1: module fix + 16.50 sidebar fold; v1.2.0: polish, heatmaps, currency-correct number cards | CHANGELOG 1.0.1 / 1.2.0 (#15) |
| Legacy Arabic print «كارت تشغيل شهري» | v1.0.0 | ✅ | ✅ | ⚠️ **Deprecated** (default on new installs → Card Monthly Card Print) | ⚠️ | ⚠️ existing site default kept on upgrade (#65) | ✅ | ✅ | ✅ | — | CHANGELOG 1.2.1 Known limitations / 1.2.2 Security |
| Frappe 16.50/16.51 migrate compatibility | v1.0.1 | ❌ **Not Supported** (migrate fails ≥16.51) | ✅ | ✅ | ✅ | ✅ | ✅ (16.51.1 Verified) | ✅ | ✅ | — | CHANGELOG 1.0.1 Fixed |
| Pre-16.50 Frappe minors (16.33/16.36) | v1.0.0 | ✅ Verified | ✅ Verified | **Unknown** (untested) | **Unknown** | **Unknown** | **Not Supported** | **Not Supported** | **Not Supported** | v1.2.x CI runs on 16.5x only | CHANGELOG 1.2.0 Upgrade notes |
| English-source UI + full Arabic translation | v1.2.0 (v1.1 line) | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | CARD strings only in `card/locale` (guard test); app name "Card" never translated | CHANGELOG 1.2.0 Added |
| Rental directions (in/out/sub-rental/owned) + customer side | v1.2.0 | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | CHANGELOG 1.2.0 Added |
| Customer registry + 2 customer reports | v1.2.0 | ❌ | ❌ | ✅ | ⚠️ customer net used (was gross) | ⚠️ same isolation change as supplier registry | ✅ | ✅ | ✅ | — | PR #27; #23 |
| Card Settings + Card Company Settings; Card Manager/Card User roles | v1.2.0 | ❌ | ❌ | ✅ | ✅ | ⚠️ Accounts Manager can save accounting fields; policy fields → level 2 | ⚠️ + workshop/storage cost centers per company | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | — | CHANGELOG 1.2.2 Security |
| Three rate bases (hourly/daily/monthly, hours-billed) | v1.2.0 | ❌ (hourly logic only) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Full-day billing for the daily basis: **Planned**, not shipped | README Billing rule; CHANGELOG Unreleased |
| Diesel management (Project Diesel Fill, policy, 2 diesel reports) | v1.2.0 | ❌ | ❌ | ✅ | ✅ | ⚠️ estimated vs recorded litres labelled; cost totals still mixed (#33) | ✅ | ✅ | ✅ | v4.2.0: metered session (meter photos, readings, totalizer check), operations approval before submit, WhatsApp session import as drafts | CHANGELOG 1.2.2 Fixed/Known limitations |
| Transport management (Equipment Transport, per-project prices, report) | v1.2.0 | ❌ | ❌ | ✅ | ✅ | ✅ change history added | ⚠️ multi-machine, destinations, cost bearer, destination cost center | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | —; v4.1.2: simpler form (route, cost, collapsible Linked Records); v4.3.0: responsibility replaces the editable cost bearer | CHANGELOG 1.2.0 / 1.2.2 |
| Card Equipment accounting dimension + guard report + period lock | v1.2.0 | ❌ | ❌ | ✅ (manual setup) | ✅ | ✅ | ✅ | ✅ | ✅ | Dimension creation stays a manual step | CHANGELOG 1.2.0 / 1.2.2 Migration |
| Monthly draft supplier/customer postings (opt-in) + GL Posting Log | v1.2.0 | ❌ | ❌ | ✅ | ✅ | ⚠️ endpoints company-scoped (#36); log permanent/immutable (#57); amend-chain + name-reuse fixes | ⚠️ one transport line per machine share | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | —; v4.3.0: integrity guards and project cost centers | CHANGELOG 1.2.2 |
| Report suite (9 reports) company-scoped, GL figures gated by GL-read roles | v1.2.0 | ❌ (2 reports, ungated) | ❌ | ✅ | ✅ | ✅ project titles for operational roles (#29) | ⚠️ transport/operating cost count Company-borne moves only | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | — | PR #14; PR #30 |
| Report filters usable by operational roles (no ERPNext grants) | v1.2.1 | ❌ | ❌ | ❌ (#21) | ✅ | ✅ | ✅ | ✅ | ✅ | Supplier/customer filters link to CARD registries; Autocomplete company/project | PR #22 |
| RTL print formats (monthly card, diesel, transport) | v1.2.0 | ❌ | ❌ | ✅ | ✅ money-side and label fixes | ✅ | ✅ | ✅ | ✅ | PR #26; v4.4.0: standard print style, print language and page direction (also the tool handover receipt); fixture `كارت تشغيل شهري` no longer forced to English; v4.4.1: PDF through the Chrome generator (wkhtmltopdf broke Arabic letter joining) | CHANGELOG 1.2.1; CHANGELOG 4.4.0; PR #172; CHANGELOG 4.4.1; PR #175 |
| Link-query endpoints `card_projects_query` / `card_companies_query` | v1.2.0 | ❌ | ❌ | ✅ | **Removed/Replaced** by `card_project_options` / `card_company_options` | ❌ (replaced) | ❌ (replaced) | ❌ (replaced) | ❌ (replaced) | Breaking only for custom clients | CHANGELOG 1.2.1 Compatibility |
| Multi-company isolation (registries, posting endpoints) | v1.2.2 | n/a (single-party scope) | n/a | ❌ (#23 open) | ❌ (#23 open) | ✅ | ✅ | ✅ | ✅ | — | CHANGELOG 1.2.2 Security |
| Read-only current project/assignment date + optional daily location sync | v1.2.2 | ❌ | ❌ | ❌ | ❌ | ✅ (job **off by default**) | ✅ | ✅ | ✅ | — | CHANGELOG 1.2.2; `card/hooks.py` scheduler_events |
| Idempotent installer for legacy sites | v1.0.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | CHANGELOG 1.0.0 |
| CI (unit tests, linters, CodeQL, Semgrep) + auto-release from CHANGELOG | v1.2.0 | ❌ (basic Actions) | ❌ | ✅ | ✅ | ✅ Node 24 actions, docs-PR checks, release.yml | ✅ | ✅ | ✅ | — | PRs #3/#5, #63, #66; `.github/workflows/` |
| CARD launcher (Dock + 9 sidebars) | v3.0.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | needs frappe Dock/Sidebar (16.51.1 Verified); v4.1.2: entries hidden by a site dock layer saved before v3.0.0 restored by patch | `card/dock/card/card.json`; CHANGELOG 3.0.0 |
| Multi-machine transport, destinations, automatic From, cost bearer | v3.0.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | cost charged to the destination's cost center | CHANGELOG 3.0.0 Added |
| Monthly card project from approved transports | v3.0.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | **Breaking**: no transport → no card | CHANGELOG 3.0.0 Breaking changes |
| Equipment details from the ERPNext Asset | v3.0.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | patch renames linked equipment to the Asset name | CHANGELOG 3.0.0 Migration |
| Dated unit components (replace / move) | v3.0.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | refused inside an approved card period | CHANGELOG 3.0.0 Added |
| Equipment needs: operator page, supervisor review, management approval → draft Material Requests | v4.0.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | approver also needs ERPNext Material Request create right; drafts only | CHANGELOG 4.0.0 Added |
| Employee tool custody (one shared custody store) | v4.0.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | loss/damage flagged for review, never a salary deduction | CHANGELOG 4.0.0 Added |
| Materials reports (needs summary, consumption, worker custody, repeat requests) | v4.0.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | follow company and project record permissions | CHANGELOG 4.0.0 Added/Security |
| Card Supervisor / Card Operator roles; bn/hi/ur operator strings | v4.0.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | operators linked to an Employee get ERPNext's Employee role (Desk) | CHANGELOG 4.0.0 Known limitations |
| Unique chassis / plate number per company (FR-080) | v4.1.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | Normalised comparison; legacy duplicates kept and listed in the Error Log; Duplicate does not copy the numbers | PR #129; CHANGELOG 4.1.0 |
| Upgrade rehearsal from v1.0.1 in CI | v4.1.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | Synthetic data on frappe 16.51.1 / ERPNext 16.50.0 | PR #130 |
| CARD Mobile `/cdms` (operator requests) | v4.1.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ not tested on real phones | Full phone app planned from v4.2.0 | PR #76, #89, #112 |
| Catalog search (phase 1) + parts fitment (phase 2a) | v4.1.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | Fitment 2b (#110) not included | PR #106, #108, #109 |
| Tool handover confirmation + Tool Custody screen | v4.1.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | v4.1.1: item search in the New Handover dialog and the page filter no longer requires an ERPNext Item permission (scoped `item_query` endpoint) | PR #114, #115, #116; v4.1.1 fix |
| Diesel price lock per company | v4.1.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | Typed prices on new fills refused; exception role with reason | PR #79 |
| Posting integrity: signed drafts, copy guard, hand-booked invoice link/review, diesel VAT basis (FR-090) | v4.3.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **Breaking**: drafts built before 4.3.0 must be rebuilt; empty VAT basis refuses the build for a VAT-registered supplier | PR #151; CHANGELOG 4.3.0 Fixed |
| Project/assignment cost center on every CARD posting line (FR-091) | v4.3.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **Breaking**: missing, unusable or conflicting cost center, and company-paid moves to or from a project, refuse the build | PR #152; CHANGELOG 4.3.0 Improved |
| Transport cost responsibility + financial decision + Transport Accounting Review (FR-093) | v4.3.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **Breaking**: `responsibility` required, `cost_borne_by` no default; customer invoicing, supplier recovery and posting of these transports disabled | PR #154; CHANGELOG 4.3.0 Added/Migration |
| Diesel Invoice Reconciliation report, read-only (FR-092) | v4.3.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Accounts Manager / System Manager | PR #153 |
| Equipment Meter Reconciliation and Asset Mapping Review reports, read-only; Create from Asset with ownership (FR-094, FR-095) | v4.3.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | No baseline set; nothing created by the review | PR #155 |
| Card Equipment financial privacy, Asset prefill by field level (FR-096, FR-097) | v4.3.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **Breaking** for readers: four fields at level 2, supplier hourly rate at level 1; new Versions masked | PR #156, #157; CHANGELOG 4.3.0 Security |
| Night-shift customer rate (FR-109) | v4.3.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Night-shift cards of customer-billing equipment mirror it; day cards unchanged | PR #167 |
| A4 print of the Equipment Supplier Statement (FR-089) | v4.3.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Choose Landscape in the PDF dialog; v4.4.0: standard print style, direction from the user's language, totals under the amount columns, Additions/Deductions only when used, no equipment no./rate columns; v4.4.1: short printed totals (opening + period charges − payments = closing, picked by stable summary keys), reconciliation figures on the screen report only; the PDF button still renders with wkhtmltopdf (use browser Print for Arabic); v4.4.2: every card of the period printed, totals from the cards only (cards net; not yet invoiced through CARD, before VAT, when positive), no ledger lines, issued-by footer, full From/To dates, Noto Sans Arabic; v4.4.3: the PDF button renders with the Chrome PDF generator (server-built page, filters only), A4 portrait on one page, font kept under a site print style | PR #150; PR #171; PR #175; PR #178; PR #180 |
| Print language and direction for CARD prints, Jinja `card_print_is_rtl` (FR-055, FR-045, FR-089) | v4.4.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Display only; code-only rollback to v4.3.0 needs a forced re-import of the five standard formats | PR #171, #172; CHANGELOG 4.4.0 |
| Settlement phase 1: accrual journal link and Card Settlement Status report (FR-110) | v4.5.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Accountant-only link (POST); report for System Manager / Accounts Manager with ledger access; no GL write | PR #182 |
| Read endpoints GET-only; diesel fill company isolation (FR-098) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Six read functions refuse POST/PUT/DELETE; cross-company read, write and share of a fill refused | PR #161 |
| Attachment validation and privacy (FR-099) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | JPEG/PNG/WebP/PDF by content, 10 MB; transport and equipment documents private to their record; HEIC refused | PR #162 |
| Project-tank diesel posts at project level (FR-100) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | One project-level line; older drafts with a tank fill refused on submit until rebuilt | PR #163 |
| Optional meter extraction in Project Diesel Fill (FR-101) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Off by default (site_config keys); IP-literal worker URL only | PR #164 |
| Card values on the CARD workspace (FR-111) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Supplier, customer and internal series; internal rate fields (level 2) | PR #185 |
| Equipment Partial Margin, Unbilled Card Work, Equipment Maintenance Cost reports (FR-112 to FR-114) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Read-only; margin and maintenance need the Card Equipment dimension | PR #188 |
| Owned-only units, derived component flag, initial place, move-day rule (FR-115 to FR-117) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Patch `v4_6_0.derive_unit_component_flag`; per-company settings, defaults unchanged | PR #187 |
| Configurable stop reasons, responsible party, Equipment Downtime report (FR-118) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Patch `v4_6_0.seed_stop_reasons` (non-billable); billing unchanged until a reason is billable | PR #194 |
| CARD Monthly Posting page with a preview (FR-119) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Preview GET, writes nothing; posting unchanged | PR #193 |
| Other-party transport responsibility, agreed amount (FR-120) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Never company cost, never posted | PR #190 |
| Reviewer is not the approver on equipment needs (FR-121) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Enforced by default; no role exempt | PR #189 |
| Equipment status guard per company (FR-122) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Warn only by default | PR #191 |
| Mandatory cancel reason, override comments (FR-123) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Workflow cancel action and List bulk cancel refused for the three doctypes | PR #197 |
| Dead settings retired (FR-124) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Hidden, read only, values kept | PR #198 |
| Effective-dated diesel price schedule (FR-125) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Patch `v4_7_0.seed_diesel_price_schedule`; `diesel_unit_price` read-only once scheduled | PR #195 |
| Diesel fill project check per company (FR-126) | v4.6.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Warn only by default | PR #196 |
| Portal catalog under ERPNext v16.54.0+ Company Restriction (FR-076 fix) | v4.3.0 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Earlier versions: empty catalog for Card portal roles on ERPNext ≥ 16.54.0; Partially Verified (CI only) | PR #169 |

## Reading the matrix

- A ⚠️ means the feature exists but with a caveat that matters for that version — read the note and
  the linked per-version page before relying on it.
- "n/a" = the concept does not apply at that version (e.g. company isolation before the customer/
  multi-company surface existed).
- Anything not listed on a tag's page or in this matrix should be treated as **Unknown** for that
  version — do not assume a capability from an issue or a plan.

Per-version detail: [v1.0.0](v1.0.0.md) · [v1.0.1](v1.0.1.md) · [v1.2.0](v1.2.0.md) ·
[v1.2.1](v1.2.1.md) · [v1.2.2](v1.2.2.md) · [v3.0.0](v3.0.0.md) · [v4.3.0](v4.3.0.md) · [v4.4.0](v4.4.0.md) · [v4.4.1](v4.4.1.md) · [v4.4.2](v4.4.2.md) · [v4.4.3](v4.4.3.md) · [v4.5.0](v4.5.0.md) · [v4.6.0](v4.6.0.md) · Guidance: [Which version should I use?](WHICH-VERSION.md)
