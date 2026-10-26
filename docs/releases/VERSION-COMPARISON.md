# CARD — Version Comparison Matrix

Feature-by-feature comparison of every published release. **Status values:** ✅ supported ·
⚠️ supported with the noted caveat · ❌ not present · labels **Verified / Partially Verified /
Unknown / Not Supported / Deprecated / Removed** per the
[release policy](RELEASE-POLICY.md). Evidence column: CHANGELOG section, PR/issue, or file path at
the tag (`git show <tag>:<path>`).

| Feature | First in | v1.0.0 | v1.0.1 | v1.2.0 | v1.2.1 | v1.2.2 | v3.0.0 | v4.0.0 | v4.1.0 | Behaviour changes / notes | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Equipment master (type, category, ownership, supplier, company) | v1.0.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ Asset-linked equipment: name/brand/type from the Asset (read-only) | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | v1.2.2: commercial terms + control fields write-protected (Card Manager), change reason required | CHANGELOG 1.0.0 / 1.2.2 Security; `card/card/doctype/card_equipment` |
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
| Diesel management (Project Diesel Fill, policy, 2 diesel reports) | v1.2.0 | ❌ | ❌ | ✅ | ✅ | ⚠️ estimated vs recorded litres labelled; cost totals still mixed (#33) | ✅ | ✅ | ✅ | — | CHANGELOG 1.2.2 Fixed/Known limitations |
| Transport management (Equipment Transport, per-project prices, report) | v1.2.0 | ❌ | ❌ | ✅ | ✅ | ✅ change history added | ⚠️ multi-machine, destinations, cost bearer, destination cost center | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | —; v4.1.2: simpler form (route, cost, collapsible Linked Records) | CHANGELOG 1.2.0 / 1.2.2 |
| Card Equipment accounting dimension + guard report + period lock | v1.2.0 | ❌ | ❌ | ✅ (manual setup) | ✅ | ✅ | ✅ | ✅ | ✅ | Dimension creation stays a manual step | CHANGELOG 1.2.0 / 1.2.2 Migration |
| Monthly draft supplier/customer postings (opt-in) + GL Posting Log | v1.2.0 | ❌ | ❌ | ✅ | ✅ | ⚠️ endpoints company-scoped (#36); log permanent/immutable (#57); amend-chain + name-reuse fixes | ⚠️ one transport line per machine share | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | — | CHANGELOG 1.2.2 |
| Report suite (9 reports) company-scoped, GL figures gated by GL-read roles | v1.2.0 | ❌ (2 reports, ungated) | ❌ | ✅ | ✅ | ✅ project titles for operational roles (#29) | ⚠️ transport/operating cost count Company-borne moves only | ⚠️ as v3.0.0 | ⚠️ as v4.0.0 | — | PR #14; PR #30 |
| Report filters usable by operational roles (no ERPNext grants) | v1.2.1 | ❌ | ❌ | ❌ (#21) | ✅ | ✅ | ✅ | ✅ | ✅ | Supplier/customer filters link to CARD registries; Autocomplete company/project | PR #22 |
| RTL print formats (monthly card, diesel, transport) | v1.2.0 | ❌ | ❌ | ✅ | ✅ money-side and label fixes | ✅ | ✅ | ✅ | ✅ | PR #26 | CHANGELOG 1.2.1 |
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

## Reading the matrix

- A ⚠️ means the feature exists but with a caveat that matters for that version — read the note and
  the linked per-version page before relying on it.
- "n/a" = the concept does not apply at that version (e.g. company isolation before the customer/
  multi-company surface existed).
- Anything not listed on a tag's page or in this matrix should be treated as **Unknown** for that
  version — do not assume a capability from an issue or a plan.

Per-version detail: [v1.0.0](v1.0.0.md) · [v1.0.1](v1.0.1.md) · [v1.2.0](v1.2.0.md) ·
[v1.2.1](v1.2.1.md) · [v1.2.2](v1.2.2.md) · [v3.0.0](v3.0.0.md) · Guidance: [Which version should I use?](WHICH-VERSION.md)
