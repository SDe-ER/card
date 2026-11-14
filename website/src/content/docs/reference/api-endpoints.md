---
title: "API endpoints"
description: "Every whitelisted CARD API method with its HTTP methods and arguments."
editUrl: false
sidebar:
  order: 3
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| Module | API endpoints |
|---|---|
| [`card.api`](#card-api) | 12 |
| [`card.cancel_reason`](#card-cancel-reason) | 1 |
| [`card.card.dashboard_chart_source.card_monthly_values.card_monthly_values`](#card-card-dashboard-chart-source-card-monthly-values-card-monthly-values) | 1 |
| [`card.card.doctype.card_equipment.card_equipment`](#card-card-doctype-card-equipment-card-equipment) | 5 |
| [`card.card.doctype.card_monthly_card.card_monthly_card`](#card-card-doctype-card-monthly-card-card-monthly-card) | 1 |
| [`card.card.doctype.card_settings.card_settings`](#card-card-doctype-card-settings-card-settings) | 2 |
| [`card.card.doctype.equipment_transport.equipment_transport`](#card-card-doctype-equipment-transport-equipment-transport) | 3 |
| [`card.card.doctype.project_diesel_fill.project_diesel_fill`](#card-card-doctype-project-diesel-fill-project-diesel-fill) | 5 |
| [`card.card.report.equipment_supplier_statement.statement_pdf`](#card-card-report-equipment-supplier-statement-statement-pdf) | 1 |
| [`card.card_value`](#card-card-value) | 7 |
| [`card.catalog`](#card-catalog) | 2 |
| [`card.daily_log_generation`](#card-daily-log-generation) | 1 |
| [`card.diesel`](#card-diesel) | 1 |
| [`card.diesel_reconciliation`](#card-diesel-reconciliation) | 1 |
| [`card.fitment`](#card-fitment) | 2 |
| [`card.gl.integrity`](#card-gl-integrity) | 2 |
| [`card.gl.journal_link`](#card-gl-journal-link) | 1 |
| [`card.gl.period_run`](#card-gl-period-run) | 2 |
| [`card.gl.posting`](#card-gl-posting) | 5 |
| [`card.governance_workflows`](#card-governance-workflows) | 1 |
| [`card.materials`](#card-materials) | 8 |
| [`card.mobile`](#card-mobile) | 1 |
| [`card.tool_custody`](#card-tool-custody) | 8 |


<h2 id="card-api"><code>card.api</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.api.party_figures` | GET | `party_type: str`<br/>`party: str` |
| `card.api.refresh_supplier` | POST | `supplier: str \| None = None` |
| `card.api.card_suppliers_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.api.refresh_customer` | POST | `customer: str \| None = None` |
| `card.api.card_customers_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.api.card_project_options` | GET, POST | `txt: str \| None = None`<br/>`company: str \| None = None` |
| `card.api.report_defaults` | GET | none |
| `card.api.card_company_options` | GET, POST | `txt: str \| None = None` |
| `card.api.get_only_company` | GET | none |
| `card.api.get_asset_prefill` | GET | `asset: str` |
| `card.api.create_equipment_from_asset` | POST | `asset: str`<br/>`ownership: str = 'ملك'`<br/>`save: int \| str = 0` |
| `card.api.available_assets_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |

- `party_figures` — Per-company figures of one registry party (supplier net / customer accrued = customer net), for the companies the caller may see only.
- `refresh_supplier` — Refresh one supplier, or all suppliers with submitted non-owned cards. Ported from Server Script "Card Equipment Supplier - Refresh" v1.1. System Manager only.
- `card_suppliers_query` — Link-filter query for the supplier reports: rows of the CARD supplier registry (Card Equipment Supplier, named by the supplier) with at least one Card Monthly Card in a company the user may see (drafts + submitted; cancelled excluded). The filter links to the registry — readable by every report role — because Frappe validates report Link filter values against the user's own permissions, and operational roles cannot read Supplier.
- `refresh_customer` — Refresh one customer, or all customers with submitted billing cards. Mirror of refresh_supplier. System Manager only.
- `card_customers_query` — Link-filter query for the customer reports: rows of the CARD customer registry (Card Equipment Customer, named by the customer) with at least one Card Monthly Card in a company the user may see — the owner's "customers with at least one card" rule. Links to the registry for the same reason as card_suppliers_query.
- `card_project_options` — Options for the reports' Project filter (an Autocomplete, not a Link: Frappe validates report Link filter values against the user's own permissions, and operational roles cannot read Project). Projects of the companies the user may see; the reports scope their rows by company too.
- `report_defaults` — Report filter defaults for any report role (Card Settings itself is not readable by Card User).
- `card_company_options` — Options for the reports' Company filter: the companies the user may see. An Autocomplete rather than a Link — Frappe checks Link filter values for read before select and posts a permission message for every operational user; each report validates the company server-side (resolve_company).
- `get_only_company` — The company a new CARD form takes when the user may see exactly one; else None. frappe already fills the user's default company; this covers a site with one company and no default. The field stays editable.
- `get_asset_prefill` — Values the equipment form fills from the chosen Asset (read only).
- `create_equipment_from_asset` — A Card Equipment prefilled from a submitted ERPNext Asset (maintenance plan M1: minimum input).
- `available_assets_query` — Link-filter query for Card Equipment.الأصل_في_erpnext: submitted Assets of the given company that are not Scrapped/Sold and not already linked to a Card Equipment. Only for users who may create or edit Card Equipment and may read Assets (linking needs Asset read, see CardEquipment.validate_asset_link), within the companies they may see for Card Equipment. frappe.get_list applies the Asset permissions and User Permissions.


<h2 id="card-cancel-reason"><code>card.cancel_reason</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.cancel_reason.cancel_with_reason` | POST | `doctype: str`<br/>`name: str`<br/>`reason: str \| None = None` |

- `cancel_with_reason` — The form's Cancel: store the reason and cancel the stored document in one request (a refused cancel rolls the reason back with it). Frappe's own cancel permission and the doctype's has_permission hook (company isolation) decide who may cancel.


<h2 id="card-card-dashboard-chart-source-card-monthly-values-card-monthly-values"><code>card.card.dashboard_chart_source.card_monthly_values.card_monthly_values</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get` | POST | `chart_name: str \| None = None`<br/>`chart: str \| dict \| None = None`<br/>`no_cache: bool \| int \| str \| None = None`<br/>`filters: str \| dict \| list \| None = None`<br/>`from_date: str \| None = None`<br/>`to_date: str \| None = None`<br/>`timespan: str \| None = None`<br/>`time_interval: str \| None = None`<br/>`heatmap_year: str \| int \| None = None`<br/>`refresh: bool \| int \| str \| None = None` |


<h2 id="card-card-doctype-card-equipment-card-equipment"><code>card.card.doctype.card_equipment.card_equipment</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues` | GET | `company: str \| None = None` |
| `card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag` | POST | `equipment: str` |
| `card.card.doctype.card_equipment.card_equipment.get_shift_heatmap` | GET | `name: str` |
| `card.card.doctype.card_equipment.card_equipment.replace_component` | POST | `unit: str`<br/>`component: str`<br/>`new_component: str`<br/>`date: str`<br/>`reason: str \| None = None` |
| `card.card.doctype.card_equipment.card_equipment.move_component` | POST | `unit: str`<br/>`component: str`<br/>`target_unit: str`<br/>`date: str`<br/>`reason: str \| None = None` |

- `get_unit_integrity_issues` — Existing records that break the owned-only unit rule or whose unit-component flag does not match the component tables, for the equipment the user may read (Company User Permissions apply). Read-only; nothing is changed.
- `resync_unit_component_flag` — Set one equipment's unit-component flag to the value its component rows give (for a flag the migration kept because it was ambiguous). Card Manager level: the flag is permission level 1, like the components table.
- `get_shift_heatmap` — Per-shift daily operating hours, so two-shift equipment can show the day (نهاري) and night (ليلي) activity as two separate heatmaps with distinct palettes. Mirrors get_timeline_data but also groups by the card's shift. Returns {"day": {ts: hours}, "night": {ts: hours}, "has_night": bool}.
- `replace_component` — From `date`, `new_component` takes the place of `component` in `unit`.
- `move_component` — From `date`, `component` leaves `unit` and works in `target_unit` (same project).


<h2 id="card-card-doctype-card-monthly-card-card-monthly-card"><code>card.card.doctype.card_monthly_card.card_monthly_card</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.card.doctype.card_monthly_card.card_monthly_card.get_card_context` | GET | `equipment: str`<br/>`month: str`<br/>`year: str`<br/>`project: str \| None = None` |

- `get_card_context` — V3.0.0: what the card form fills in by itself once equipment, month and year are picked — the projects the approved transports put the equipment on that month, and the days it was on the chosen (or only) project. Read-only.


<h2 id="card-card-doctype-card-settings-card-settings"><code>card.card.doctype.card_settings.card_settings</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.card.doctype.card_settings.card_settings.getdoc` | GET, POST | `doctype: str`<br/>`name: str \| int` |
| `card.card.doctype.card_settings.card_settings.get_docinfo` | GET, POST | `doc: Document \| dict \| str \| None = None`<br/>`doctype: str \| None = None`<br/>`name: str \| int \| None = None` |

- `getdoc` — Override of ``frappe.desk.form.load.getdoc``: calls the previous override in the hook chain (or Frappe's method), then removes from the Card Settings timeline of a company-restricted user every row of another company.
- `get_docinfo` — Override of ``frappe.desk.form.load.get_docinfo``: as ``getdoc``.


<h2 id="card-card-doctype-equipment-transport-equipment-transport"><code>card.card.doctype.equipment_transport.equipment_transport</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.card.doctype.equipment_transport.equipment_transport.get_equipment_location` | GET | `equipment: str` |
| `card.card.doctype.equipment_transport.equipment_transport.record_financial_decision` | POST | `transport: str`<br/>`decision: str`<br/>`customer: str \| None = None`<br/>`billing_project: str \| None = None`<br/>`billing_amount: float \| None = None`<br/>`billing_mode: str \| None = None`<br/>`billing_reference: str \| None = None`<br/>`billing_document: str \| None = None`<br/>`absorption_reason: str \| None = None`<br/>`recovery_mode: str \| None = None`<br/>`recovery_amount: float \| None = None`<br/>`note: str \| None = None`<br/>`confirmed: int \| str = 0` |
| `card.card.doctype.equipment_transport.equipment_transport.billing_customer` | GET | `transport: str`<br/>`project: str \| None = None` |

- `get_equipment_location` — The current place of one machine, shown in the transport form as soon as it is picked.
- `record_financial_decision` — P1-2 (Owner D3/D4/D6/D7/D8, 2026-10-31): an Accounts Manager records the financial decision of a submitted transport whose cost the customer or the equipment supplier bears — bill the customer (agreed amount, authorization), the company absorbs it (documented reason), recover it from the equipment supplier, or reject it. Separation of duties: never the transport's creator, editor or submitter (nor those of the transport it amends). The decision is only recorded: customer billing, supplier recovery and absorption postings stay disabled until the accountant and the tax adviser decide.
- `billing_customer` — The billing project suggested for a transport's financial decision (its destination project, when that project names a customer) or the customer of the project the accountant picks — read only, for an Accounts Manager who may read the transport; the project must belong to the transport's company. The accountant confirms both before the decision is recorded.


<h2 id="card-card-doctype-project-diesel-fill-project-diesel-fill"><code>card.card.doctype.project_diesel_fill.project_diesel_fill</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable` | GET | none |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: str \| dict \| None = None` |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context` | GET | `company: str \| None = None`<br/>`date: str \| None = None` |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price` | POST | `name: str`<br/>`reason: str \| None = None` |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception` | POST | `name: str`<br/>`reason: str \| None = None` |

- `get_supplier_editable` — Whether the fill form lets the current user change the diesel supplier (read only). Fill users cannot read Card Settings, so only this yes/no leaves the server.
- `fill_link_query` — Link search of the diesel fill form for Project, Cost Center and Supplier (read only).
- `get_diesel_price_context` — What the fill form needs before saving (read only): the company price on the fill date (today when empty) and whether the current user may grant a price exception. Fill users cannot read Card Settings.
- `use_company_price` — Explicit choice on a draft without an exception (the form offers it on Needs Review drafts): replace its price with the current company price. Owner 2026-10-20: changing a saved draft's price needs the exception role, a reason and an audit.
- `remove_price_exception` — End the price exception of a saved draft: it returns to the current company price. Owner 2026-10-20: needs the exception role and a written reason; audited like every price change.


<h2 id="card-card-report-equipment-supplier-statement-statement-pdf"><code>card.card.report.equipment_supplier_statement.statement_pdf</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.card.report.equipment_supplier_statement.statement_pdf.download_pdf` | POST | `filters: str \| dict \| None = None` |

- `download_pdf` — Send the statement as a PDF file (Chrome generator). Same permissions as running and printing the report; the company is checked by the report.


<h2 id="card-card-value"><code>card.card_value</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.card_value.supplier_cost_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.customer_value_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.internal_value_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.cards_without_internal_rate_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.hours_without_internal_rate_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.loads_last_month` | POST | `filters: str \| dict \| list \| None = None` |


<h2 id="card-catalog"><code>card.catalog</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.catalog.search` | GET | `txt: str \| None = None`<br/>`item_group: str \| None = None`<br/>`brand: str \| None = None`<br/>`start: int = 0`<br/>`page_length: int = PAGE_LENGTH`<br/>`equipment: str \| None = None`<br/>`fits: int = 0` |
| `card.catalog.filter_options` | GET | `kind: str`<br/>`txt: str \| None = None`<br/>`start: int = 0`<br/>`page_length: int = PAGE_LENGTH` |

- `search` — One page of the catalogue for the search text (item code, item name, barcode, OEM number) and the filters (item group with its sub-groups, brand). ``has_more`` says whether another page exists; no total count is given. With ``equipment`` (phase 2b) every item carries its ``fit`` for that machine; ``fits`` lists only the items Confirmed for it (machine or model).
- `filter_options` — Values for the Item Group or Brand filter, searched and paged on the server, read with the user's rights (the restricted read for Card portal roles). Item Group names are translated by Frappe, so they are matched by name or by their translation.


<h2 id="card-daily-log-generation"><code>card.daily_log_generation</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.daily_log_generation.generate_monthly_cards` | POST | `company: str`<br/>`project: str`<br/>`month: str`<br/>`equipment: str \| None = None` |

- `generate_monthly_cards` — Create or update the draft monthly cards of one company, project and month (optionally one equipment) from the Approved daily logs. Never submits a card and never changes a submitted one (module docstring).


<h2 id="card-diesel"><code>card.diesel</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.diesel.get_card_diesel` | GET | `card: str` |

- `get_card_diesel` — Diesel allocated to one Card Monthly Card's equipment for its project + month, with its recorded (direct fill) and estimated (hours split) parts. Display only; it is NEVER written back and NEVER affects net_amount.


<h2 id="card-diesel-reconciliation"><code>card.diesel_reconciliation</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.diesel_reconciliation.diesel_supplier_options` | GET | `txt: str \| None = None`<br/>`company: str \| None = None` |

- `diesel_supplier_options` — Options for the report's supplier filter: suppliers of diesel sessions the user may read, in the companies the user may see for both doctypes (a list, not a Link to the Supplier master: report Link filters are checked against the user's own permissions).


<h2 id="card-fitment"><code>card.fitment</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.fitment.fit_for` | GET | `equipment: str`<br/>`items: str \| list` |
| `card.fitment.machines` | GET | `txt: str \| None = None`<br/>`start: int = 0` |

- `fit_for` — The fit of up to 50 Items for one machine (the inline item picker of CARD Mobile).
- `machines` — Machines the caller may look up in the catalog: a Desk reader's own list (his DocPerms and User Permissions apply), or an operator's own machines. Searched and paged on the server.


<h2 id="card-gl-integrity"><code>card.gl.integrity</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.gl.integrity.accept_correction` | POST | `invoice_doctype: str`<br/>`invoice: str`<br/>`reason: str` |
| `card.gl.integrity.link_supplier_invoice` | POST | `invoice: str`<br/>`sources: str \| list`<br/>`reason: str \| None = None`<br/>`accept_difference: int \| str = 0` |

- `accept_correction` — An Accounts Manager accepts a corrected cost center / account on a CARD draft. Only those fields may differ; the acceptance is tied to the exact invoice content (any later edit needs a new acceptance).
- `link_supplier_invoice` — Record that an existing supplier Purchase Invoice (booked by hand) already pays for these CARD sources. Nothing is reposted and the invoice is not changed: a Linked GL Posting Log reserves the sources so CARD never builds them again, and the sources show the invoice once it is submitted.


<h2 id="card-gl-journal-link"><code>card.gl.journal_link</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.gl.journal_link.link_accrual_journal` | POST | `journal_entry: str`<br/>`cards: str \| list`<br/>`reason: str \| None = None`<br/>`accept_difference: int \| str = 0` |

- `link_accrual_journal` — Record that a submitted supplier accrual Journal Entry already recognised these submitted supplier monthly cards. Returns the GL Posting Log name.


<h2 id="card-gl-period-run"><code>card.gl.period_run</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.gl.period_run.build_run` | POST | `company: str`<br/>`month: str`<br/>`year: str` |
| `card.gl.period_run.period_run_status` | GET | `company: str`<br/>`month: str`<br/>`year: str` |

- `build_run` — Build (or rebuild) the draft period run of a company-month and return its name. A draft is saved again, which rebuilds its snapshot; a new run amends the latest cancelled run of the month, so its version and its preparers follow on. Card Manager or System Manager; Frappe's create/write permission and the company scope apply (no permission is skipped).
- `period_run_status` — The active run of a company-month and whether it is current and validly approved. Reads only (it rebuilds the live snapshot on each call). The totals are returned only to a user who may read the run's amounts (permlevel 1).


<h2 id="card-gl-posting"><code>card.gl.posting</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.gl.posting.rebuild_month` | POST | `company: str`<br/>`party_type: str`<br/>`party: str`<br/>`month: str`<br/>`year: str`<br/>`reviewed_invoices: str \| list \| None = None` |
| `card.gl.posting.post_month` | POST | `company: str`<br/>`party_type: str`<br/>`party: str`<br/>`month: str`<br/>`year: str`<br/>`reviewed_invoices: str \| list \| None = None` |
| `card.gl.posting.posting_month_parties` | GET | `company: str`<br/>`month: str`<br/>`year: str` |
| `card.gl.posting.preview_month` | GET | `company: str`<br/>`party_type: str`<br/>`party: str`<br/>`month: str`<br/>`year: str` |
| `card.gl.posting.posting_period_run` | GET | `company: str`<br/>`month: str`<br/>`year: str` |

- `rebuild_month` — Desk entry point for rebuilding a draft posting after late documents.
- `post_month` — Desk entry point (S4 wires the button). Card Manager / System Manager only. reviewed_invoices: supplier invoices an accountant declares unrelated (P0).
- `posting_month_parties` — Posting screen: the parties of the month with their posting status. Read only. Each side is listed only when the caller may build that side's postings.
- `preview_month` — Posting screen: the lines the next post (or rebuild) would create. Read only — nothing is inserted, saved, reserved or logged; post_month / rebuild_month write.
- `posting_period_run` — Posting screen: whether the company requires an approved period run before posting, the state of the month's run and why posting is refused. Read only (it rebuilds the run's live snapshot); no amounts. The same role and company checks as the party list.


<h2 id="card-governance-workflows"><code>card.governance_workflows</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.governance_workflows.return_for_correction` | POST | `doctype: str`<br/>`name: str`<br/>`reason: str \| None = None` |

- `return_for_correction` — The form's "Return for Correction": apply the Workflow action with its mandatory reason in one request. Frappe's ``apply_workflow`` checks the transition, the role and the document permission.


<h2 id="card-materials"><code>card.materials</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.materials.review_stock` | GET | `review: str` |
| `card.materials.pull_requests` | POST | `review: str` |
| `card.materials.approve_review` | POST | `review: str` |
| `card.materials.close_tool_handover` | POST | `custody: str`<br/>`reason: str` |
| `card.materials.make_tool_handover` | POST | `review_item: str` |
| `card.materials.get_portal_context` | GET | none |
| `card.materials.search_items` | GET | `txt: str \| None = None` |
| `card.materials.submit_needs` | POST | `equipment: str`<br/>`items: str \| list`<br/>`notes: str \| None = None` |

- `review_stock` — Stock hint per review line, read live with the reader's rights. The hint is never stored on the review (F2): a stored figure would show stock to every reader of the review. A line without an item, or in a warehouse the reader may not see, has no hint.
- `pull_requests` — Add every submitted, pending request line of the review's project (and dates) that no other review holds. Requested quantities are copied, never edited.
- `approve_review` — Management approval: every approved line goes into a draft ERPNext Material Request (Purchase, or Material Issue for parts from the store), with item, project, cost center and the equipment dimension on each row. Every approved tool line also gets a draft custody Handover for its worker: approval moves no stock and gives nobody a tool; the store side confirms the physical handover later. All stay drafts.
- `close_tool_handover` — The worker did not take the tool: the draft is closed with a reason, never submitted; nothing is counted or moved. A replacement draft is made only by a Card Manager.
- `make_tool_handover` — Card Manager only (Owner H-2): a replacement draft for the tools of an approved line that are not handed over yet, after a documented failed handover (closed or cancelled).
- `search_items` — Items an operator may pick, by code, name, barcode or OEM number: 20 at most, code, name and unit only. Operators have no Item read permission; this is the one deliberate exception, so they can name what their machine needs (G1). The rules and User Permissions are those of the catalog search (``card.catalog``), so the inline list never shows an item the catalog hides.
- `submit_needs` — The operator's own request for one of his machines, submitted at once.


<h2 id="card-mobile"><code>card.mobile</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.mobile.get_session_context` | GET | none |

- `get_session_context` — The signed-in user's CARD Mobile context. Reads only.


<h2 id="card-tool-custody"><code>card.tool_custody</code></h2>

| Method path | HTTP methods | Arguments |
|---|---|---|
| `card.tool_custody.context` | GET | none |
| `card.tool_custody.view` | GET | `tab: str = 'awaiting'`<br/>`employee: str \| None = None`<br/>`item_code: str \| None = None`<br/>`start: int = 0` |
| `card.tool_custody.employee_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.tool_custody.employee_company` | GET | `employee: str` |
| `card.tool_custody.store_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.tool_custody.item_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.tool_custody.confirm` | POST | `custody: str`<br/>`receipt: str \| None = None`<br/>`qty: float \| None = None`<br/>`serial_no: str \| None = None` |
| `card.tool_custody.move` | POST | `movement: str`<br/>`employee: str`<br/>`item_code: str`<br/>`qty: float`<br/>`to_employee: str \| None = None`<br/>`warehouse: str \| None = None`<br/>`serial_no: str \| None = None` |

- `context` — What the screen shows this user: tabs, default tab (Owner U-5) and the main buttons.
- `view` — One page of a tab. Reads only.
- `employee_query` — Link query for the screen's employee fields: active employees, name and full name only. Filters: `company` (a transfer stays in the worker's company), `exclude` (the worker himself), `any_status` (the page filter).
- `employee_company` — The company of an employee the screen may offer (the same scope as `employee_query`), so the movement dialog fills in that company's store and searches only its stores. Reads only.
- `store_query` — Link query for the screen's store field: enabled stores (not groups) the tools move from.
- `item_query` — Link query for the screen's item field: stock tools only.
- `confirm` — Confirm a waiting Handover, Return or Transfer in one step: quantity, serial no and the signed receipt, then the standard Submit (all of the controller's rules run).
- `move` — A new movement from the screen, saved as a draft with its defaults filled in (store from Card Settings; for a Handover the worker's machine and its project). It is confirmed with `confirm`, after its receipt is printed and signed (the receipt names this record).
