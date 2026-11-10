# CARD role and action matrix

FR-129 (#51, #35, #54). What each CARD DocType and each `@frappe.whitelist` endpoint allows, to which roles, how
company B's records stay out of a company-A user's reach, and what each endpoint writes. The two tables below are
generated from the source by `card/tests/test_bola_matrix.py`; `test_matrix_document_matches_the_source` fails when
they drift from the DocType JSON files, `card/hooks.py` or the endpoint table in that module.

Regenerate both tables after a DocType permission, hook or endpoint change (from a development bench directory;
no site is needed), then paste each output between its markers:

```bash
env/bin/python -c "from card.tests.test_bola_matrix import render_doctype_matrix as r; print(r())"
env/bin/python -c "from card.tests.test_bola_matrix import render_endpoint_matrix as r; print(r())"
```

## Sources

- Roles and rights: the `permissions` of every `card/card/doctype/*/*.json` (level 0 in the action columns, higher
  levels under "Field levels"). Roles used: System Manager, Accounts Manager, Accounts User, Card Manager, Card User,
  Card Supervisor, Card Operator, Stock Manager, Stock User, Purchase User. CARD creates the four Card roles
  (`card/install.py` `CARD_ROLES`); the others are Frappe / ERPNext roles.
- Company isolation: a `company` Link field (Frappe applies Company User Permissions to it), and the
  `has_permission` / `permission_query_conditions` hooks of `card/hooks.py`.
- Endpoints: every `@frappe.whitelist` function in `card/` (tests excluded), found by the guard test
  `test_every_whitelisted_function_is_in_the_table`; the HTTP methods are checked against the decorators by
  `test_table_methods_match_the_decorators`.
- "(own)" after a role means an `if_owner` right. A child table has no rights of its own: its parent's apply.

## DocTypes

<!-- doctype-matrix:start -->
| DocType | Kind | Read | Write | Create | Submit | Cancel | Delete | Field levels | Company isolation |
|---|---|---|---|---|---|---|---|---|---|
| Card Adjustment Type | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Card Company Settings | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Card Diesel Price | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Card Equipment | Master | System Manager, Card Manager, Card User, Accounts Manager, Card Supervisor | System Manager, Card Manager, Card User | System Manager, Card Manager | - | - | System Manager | L1 read: System Manager, Card Manager, Card User, Accounts Manager; write: System Manager, Card Manager<br>L2 read: System Manager, Card Manager, Accounts Manager; write: System Manager, Card Manager | Company User Permission on `company` |
| Card Equipment Assignment | Master | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager | System Manager, Card Manager | - | - | System Manager | - | has_permission `has_assignment_permission`; permission_query_conditions `assignment_query_conditions` |
| Card Equipment Category | Master | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager, Card User | System Manager, Card Manager, Card User | - | - | System Manager | - | None (global master) |
| Card Equipment Component | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Card Equipment Customer | Master | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager | System Manager, Card Manager | - | - | System Manager | - | has_permission `has_registry_permission`; permission_query_conditions `customer_query_conditions` |
| Card Equipment Make | Master | System Manager, Card Manager, Card Supervisor, Card User, Accounts Manager | System Manager, Card Manager | System Manager, Card Manager | - | - | - | - | None (global master) |
| Card Equipment Model | Master | System Manager, Card Manager, Card Supervisor, Card User, Accounts Manager | System Manager, Card Manager | System Manager, Card Manager | - | - | - | - | None (global master) |
| Card Equipment Part | Master | System Manager, Card Manager, Card Supervisor | System Manager, Card Manager, Card Supervisor | System Manager, Card Manager, Card Supervisor | - | - | - | - | Company User Permission on `company`; has_permission `has_fitment_permission`; permission_query_conditions `fitment_query_conditions` |
| Card Equipment Supplier | Master | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager | System Manager, Card Manager | - | - | System Manager | - | has_permission `has_registry_permission`; permission_query_conditions `supplier_query_conditions` |
| Card Equipment Type | Master | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager, Card User | System Manager, Card Manager, Card User | - | - | System Manager | - | None (global master) |
| Card Location Cost Center | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Card Monthly Card | Submittable | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager, Card User | System Manager, Card Manager, Card User | System Manager, Card Manager | System Manager, Card Manager | System Manager | - | Company User Permission on `company`; has_permission `has_card_permission` |
| Card Monthly Card Adjustment | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Card Monthly Card Day | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Card Project Transport Price | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Card Settings | Single | System Manager, Accounts Manager, Card Manager | System Manager, Accounts Manager | System Manager | - | - | - | L1 read: System Manager, Accounts Manager; write: System Manager, Accounts Manager<br>L2 read: System Manager, Accounts Manager, Card Manager; write: System Manager | Single: role permissions only |
| Diesel Fill Equipment | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Employee Tool Custody | Submittable | System Manager, Card Manager, Stock Manager, Card Supervisor, Card User | System Manager, Card Manager, Stock Manager, Card Supervisor | System Manager, Card Manager, Stock Manager, Card Supervisor | System Manager, Card Manager, Stock Manager, Card Supervisor | System Manager, Card Manager, Stock Manager | System Manager, Card Manager | - | Company User Permission on `company`; has_permission `has_custody_permission` |
| Equipment Needs Request | Submittable | System Manager, Card Manager, Card Supervisor, Card Operator, Card User | System Manager, Card Manager, Card Supervisor, Card Operator | System Manager, Card Manager, Card Supervisor, Card Operator | System Manager, Card Manager, Card Supervisor, Card Operator | System Manager, Card Manager, Card Supervisor | System Manager, Card Manager | - | Company User Permission on `company`; has_permission `needs_request_permission`; permission_query_conditions `needs_request_query` |
| Equipment Needs Request Item | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Equipment Needs Review | Submittable | System Manager, Card Manager, Card Supervisor, Card User | System Manager, Card Manager, Card Supervisor | System Manager, Card Manager, Card Supervisor | System Manager, Card Manager, Card Supervisor | System Manager, Card Manager, Card Supervisor | System Manager, Card Manager | - | Company User Permission on `company` |
| Equipment Needs Review Item | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Equipment Transport | Submittable | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager, Card User | System Manager, Card Manager, Card User | System Manager, Card Manager | System Manager, Card Manager | System Manager | L1 read: System Manager, Card Manager, Accounts Manager; write: - | Company User Permission on `company`; has_permission `has_transport_permission` |
| Equipment Transport Item | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| GL Posting Log | Master | System Manager, Accounts Manager, Card Manager | - | - | - | - | - | - | Company User Permission on `company` |
| GL Posting Source | Child | - | - | - | - | - | - | - | Child table: the parent's permissions |
| Project Diesel Fill | Submittable | System Manager, Card Manager, Card User, Accounts Manager | System Manager, Card Manager, Card User | System Manager, Card Manager, Card User | System Manager, Card Manager | System Manager, Card Manager | System Manager | L1 read: System Manager, Card Manager, Card User, Accounts Manager; write: System Manager, Card Manager | Company User Permission on `company`; has_permission `has_diesel_fill_permission` |
<!-- doctype-matrix:end -->

## Endpoints

"Gate" is the check the endpoint itself runs before it reads or writes. "Company isolation" is how a user limited
to company A is kept from company B's records through that endpoint.

<!-- endpoint-matrix:start -->
| Endpoint | HTTP | Gate (server check) | Company isolation | Side effects |
|---|---|---|---|---|
| `card.api.available_assets_query` | GET | Card Equipment create or write by role; Asset read beyond select | query_companies(filters, Card Equipment); frappe.get_list on Asset | None (read only) |
| `card.api.card_company_options` | GET, POST | assert_report_role | permitted_companies (Company User Permission) | None (read only; also POST because the Autocomplete control posts) |
| `card.api.card_customers_query` | GET | assert_report_role | query_companies(filters) / permitted_companies (Company User Permission) | None (read only) |
| `card.api.card_project_options` | GET, POST | assert_report_role | query_companies (requested company only when permitted) | None (read only; also POST because the Autocomplete control posts) |
| `card.api.card_suppliers_query` | GET | assert_report_role | query_companies(filters) / permitted_companies (Company User Permission) | None (read only) |
| `card.api.create_equipment_from_asset` | POST | Card Equipment create; Asset read on the record; insert with the user's own permissions | Asset read on the record (Company User Permission); company taken from the Asset | With save=1 and nothing missing: inserts one Card Equipment; otherwise returns the prefilled values |
| `card.api.get_asset_prefill` | GET | Card Equipment read; Asset read on the record | frappe.has_permission(Asset, read, asset) (Company User Permission); fields filtered by Card Equipment read levels | None (read only) |
| `card.api.get_only_company` | GET | Company read or select, else None | frappe.get_list on Company (Company User Permission) | None (read only) |
| `card.api.party_figures` | GET | assert_report_role; read on the registry row (has_registry_permission) | has_registry_permission (party with a card in a permitted company); figures limited to permitted_companies() | None (read only) |
| `card.api.refresh_customer` | POST | System Manager role (frappe.throw otherwise) | None: global registry, no company field | Inserts or saves Card Equipment Customer rows (aggregates cleared); may rename a misnamed row |
| `card.api.refresh_supplier` | POST | System Manager role (frappe.throw otherwise) | None: global registry, no company field | Inserts or saves Card Equipment Supplier rows (aggregates cleared); may rename a misnamed row |
| `card.api.report_defaults` | GET | assert_report_role | None: two Card Settings flags, no company data | None (read only) |
| `card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get` | POST | Dashboard Chart read when named; Card Monthly Card read | frappe.get_list on Card Monthly Card / Card Equipment (Company User Permission); no shared cache | None (read only; POST because the chart widget posts) |
| `card.card.doctype.card_equipment.card_equipment.get_shift_heatmap` | GET | Card Equipment read on the record; Card Monthly Card read | frappe.has_permission on the record (Company User Permission) | None (read only) |
| `card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues` | GET | Card Equipment read | frappe.get_list on Card Equipment (Company User Permission) | None (read only) |
| `card.card.doctype.card_equipment.card_equipment.move_component` | POST | write on both units and write level of components (level 1) | doc.check_permission on both records (Company User Permission) | Closes the row in the source unit, appends it to the target unit; saves both; syncs flags |
| `card.card.doctype.card_equipment.card_equipment.replace_component` | POST | write on the unit and write level of components (level 1); read on the new component | doc.check_permission on both records (Company User Permission) | Closes one component row and appends another; saves the unit |
| `card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag` | POST | write on the record and write level of is_unit_component (level 1) | doc.check_permission(write) (Company User Permission) | Sets is_unit_component on the listed equipment |
| `card.card.doctype.card_monthly_card.card_monthly_card.get_card_context` | GET | Card Equipment read on the record | doc.check_permission(read) (Company User Permission) | None (read only) |
| `card.card.doctype.equipment_transport.equipment_transport.billing_customer` | GET | Accounts Manager role; read on the transport | doc.check_permission(read) (has_transport_permission); project must be of the transport's company | None (read only) |
| `card.card.doctype.equipment_transport.equipment_transport.get_equipment_location` | GET | Card Equipment read on the record | doc.check_permission(read) (Company User Permission) | None (read only) |
| `card.card.doctype.equipment_transport.equipment_transport.record_financial_decision` | POST | Accounts Manager role; read on the transport; not its creator, editor or submitter | has_transport_permission and permitted_companies(Equipment Transport) | db_set of the financial decision fields; one Version; one Info Comment |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query` | GET | Project Diesel Fill create or write | form company must be in permitted_companies(Project Diesel Fill); User Permissions of the linked doctype | None (read only) |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context` | GET | Project Diesel Fill read | company must be in permitted_companies(Project Diesel Fill), else price 0 | None (read only) |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable` | GET | Project Diesel Fill read | None: a yes/no answer about the session user | None (read only) |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception` | POST | write on the fill; diesel_price_exception_role; a reason | doc.check_permission(write) (has_diesel_fill_permission) | Saves the draft fill without its price exception (audited) |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price` | POST | write on the fill; diesel_price_exception_role; a reason | doc.check_permission(write) (has_diesel_fill_permission) | Saves the draft fill with the company price (audited) |
| `card.card.report.equipment_supplier_statement.statement_pdf.download_pdf` | POST | print on the report's doctype (Card Monthly Card); the standard report run | resolve_company (Company User Permission); report rows by the user's permissions | One Access Log; the PDF in the response |
| `card.card_value.cards_without_internal_rate_last_month` | POST | Card Monthly Card read (frappe.has_permission) | frappe.get_list on Card Monthly Card / Card Equipment (Company User Permission, has_card_permission) | None (read only; POST because the number card widget posts) |
| `card.card_value.customer_value_last_month` | POST | Card Monthly Card read (frappe.has_permission) | frappe.get_list on Card Monthly Card / Card Equipment (Company User Permission, has_card_permission) | None (read only; POST because the number card widget posts) |
| `card.card_value.hours_without_internal_rate_last_month` | POST | Card Monthly Card read (frappe.has_permission) | frappe.get_list on Card Monthly Card / Card Equipment (Company User Permission, has_card_permission) | None (read only; POST because the number card widget posts) |
| `card.card_value.internal_value_last_month` | POST | Card Monthly Card read (frappe.has_permission) | frappe.get_list on Card Monthly Card / Card Equipment (Company User Permission, has_card_permission) | None (read only; POST because the number card widget posts) |
| `card.card_value.supplier_cost_last_month` | POST | Card Monthly Card read (frappe.has_permission) | frappe.get_list on Card Monthly Card / Card Equipment (Company User Permission, has_card_permission) | None (read only; POST because the number card widget posts) |
| `card.catalog.filter_options` | GET | check_catalog_user | None: Item Group and Brand are global masters | None (read only) |
| `card.catalog.search` | GET | check_catalog_user (Item read or a CARD catalog role); machine access when equipment is given | Items are global; equipment: fitment.check_equipment_access (record read or own machine) | None (read only) |
| `card.diesel.get_card_diesel` | GET | Card Monthly Card read on the record | frappe.has_permission on the record (has_card_permission) | None (read only) |
| `card.diesel_reconciliation.diesel_supplier_options` | GET | assert_report_role; report permitted; role read on Project Diesel Fill and Purchase Invoice | permitted_companies of both doctypes; frappe.get_list on Project Diesel Fill | None (read only) |
| `card.fitment.fit_for` | GET | check_catalog_user; machine access | fitment.check_equipment_access (record read, Company User Permission, or own machine) | None (read only) |
| `card.fitment.machines` | GET | check_catalog_user | frappe.get_list on Card Equipment (Company User Permission); operators: their own machines | None (read only) |
| `card.gl.integrity.accept_correction` | POST | Accounts Manager or System Manager; write on the invoice; a reason | doc.check_permission(write) and permitted_companies(sources, invoice, GL Posting Log) | db_set of accepted_signature, accepted_by, correction_reason on the GL Posting Log |
| `card.gl.integrity.link_supplier_invoice` | POST | Accounts Manager, Accounts User or System Manager; read and submit on the invoice; read on supplier and every source | permitted_companies(sources, Purchase Invoice, GL Posting Log); each source of the invoice's company | Inserts one Linked GL Posting Log |
| `card.gl.journal_link.link_accrual_journal` | POST | Accounts Manager, Accounts User or System Manager; read and submit on the Journal Entry; read on supplier and every card | permitted_companies(sources, Journal Entry, GL Posting Log); each card of the entry's company | Inserts one Linked GL Posting Log (type Journal Entry) |
| `card.gl.posting.post_month` | POST | Card Manager or System Manager; party read | _checked_endpoint_args: permitted_companies(sources, invoice, GL Posting Log) | Builds a draft Purchase / Sales Invoice and a GL Posting Log (builder inserts with ignore_permissions after the gate) |
| `card.gl.posting.posting_month_parties` | GET | Card Manager or System Manager | _checked_endpoint_args per side; parties the caller cannot read are left out | None (read only) |
| `card.gl.posting.preview_month` | GET | Card Manager or System Manager; party read | _checked_endpoint_args; review invoices listed only when readable | None (read only) |
| `card.gl.posting.rebuild_month` | POST | Card Manager or System Manager; party read | _checked_endpoint_args: permitted_companies(sources, invoice, GL Posting Log) | Rebuilds the draft Purchase / Sales Invoice and its GL Posting Log (builder inserts with ignore_permissions after the gate) |
| `card.materials.approve_review` | POST | Card Manager or System Manager; Material Request create; read on the review; not a preparer (FR-121) | doc.check_permission(read) (Company User Permission); documents made in the review's company | Inserts draft Material Requests and draft custody Handovers; db_set of the approval; request status |
| `card.materials.close_tool_handover` | POST | write on the custody record; Card Manager or the store side; not the worker; a reason | doc.check_permission(write) (Company User Permission) | Saves the draft handover as Not handed over |
| `card.materials.get_portal_context` | GET | Card Operator, Card Supervisor, Card Manager or System Manager | the session user's own Employee: his machines and his requests | None (read only) |
| `card.materials.make_tool_handover` | POST | Card Manager role; read on the review | review.check_permission(read) (Company User Permission) | Inserts one draft Employee Tool Custody (Handover); links it on the review line |
| `card.materials.pull_requests` | POST | write on the review (draft only) | doc.check_permission(write) (Company User Permission); requests of the review's project | Appends request lines and saves the draft review |
| `card.materials.review_stock` | GET | read on the review; stock shown only with role read on Bin and Warehouse | doc.check_permission(read) (Company User Permission); stock limited to the review's company | None (read only) |
| `card.materials.search_items` | GET | Card Operator, Card Supervisor, Card Manager or System Manager | None: Items are global (catalog rules and Item User Permissions) | None (read only) |
| `card.materials.submit_needs` | POST | portal role; linked Employee; the machine is operated by that Employee (check_requester) | check_requester: the machine must be the session employee's; company from the machine | Inserts and submits one Equipment Needs Request |
| `card.mobile.get_session_context` | GET | has_app_permission (portal role, or catalog-only Card User) | None: the session user's own context | None (read only) |
| `card.tool_custody.confirm` | POST | screen role; submit on the custody record (controller rules on submit) | doc.check_permission(submit) (Company User Permission) | Submits the movement; Handover / Return create and submit a Stock Entry |
| `card.tool_custody.context` | GET | Card Supervisor, Card Manager, Stock Manager or System Manager, and Employee Tool Custody read | None: flags about the session user | None (read only) |
| `card.tool_custody.employee_query` | GET | screen role and Employee Tool Custody read | query_companies(filters, Employee Tool Custody); Employee User Permissions | None (read only) |
| `card.tool_custody.item_query` | GET | screen role and Employee Tool Custody read (then Item get_all with ignore_permissions) | None: Items are global masters | None (read only) |
| `card.tool_custody.move` | POST | screen role; Employee Tool Custody create (insert with the user's own permissions) | company taken from the Employee in validate, after Frappe's create check | Inserts one draft Employee Tool Custody |
| `card.tool_custody.store_query` | GET | screen role and Employee Tool Custody read | query_companies(filters, Employee Tool Custody); Warehouse User Permissions | None (read only) |
| `card.tool_custody.view` | GET | screen role and Employee Tool Custody read | frappe.get_list on Employee Tool Custody (Company User Permission) | None (read only) |
<!-- endpoint-matrix:end -->

## Negative tests

`card/tests/test_bola_matrix.py` builds a second company B with its own project, equipment, card, transport,
diesel fill, review, custody records, invoice, journal entry, asset, employees and store, and generates per endpoint:

- `test_cross_company__*`: a company-A user with the endpoint's roles aims it at company B. The call is refused with
  `PermissionError`, or it answers without any company-B value (for lists, options and totals); nothing is written.
  Where the answer is a list, an Administrator control call proves the probe would see the company-B value.
- `test_role_refused__*`: users without the endpoint's role (no role at all, and near-miss roles) are refused;
  nothing is written.
- `test_read_makes_no_write__*` (read endpoints): an allowed company-A call runs no write query and changes no row
  count or `modified` value of the watched tables.
- `test_rest_create_other_company__*`: Frappe's own insert (`frappe.client.insert`) on the CARD DocTypes whose
  company is set in `validate`, after Frappe's create check, and that have no company `has_permission` hook.

## Open findings (reported, not fixed here)

Each is an expected-failure test, so CI stays green; an "unexpected success" means the gap was closed.

| Test | Where | Scenario |
|---|---|---|
| `test_cross_company__tool_custody_move` | `card/tool_custody.py` `move`; `employee_tool_custody.py` `EmployeeToolCustody.validate` (company from the Employee); no company hook for Employee Tool Custody in `card/hooks.py` | A Card Supervisor limited to company A calls `move` (Transfer) for two employees of company B; the draft custody movement is created in company B and the answer says `may_confirm`. Confirming it is refused (submit check on the stored company). |
| `test_rest_create_other_company__employee_tool_custody` | same as above, through `frappe.client.insert` | A user limited to company A inserts a draft movement for a company-B employee. |
| `test_rest_create_other_company__equipment_needs_request` | `equipment_needs_request.py` `EquipmentNeedsRequest.validate` (company from the equipment); no company hook | A Card Supervisor limited to company A inserts a draft request for a company-B machine and its operator. |
| `test_rest_create_other_company__equipment_needs_review` | `equipment_needs_review.py` `EquipmentNeedsReview.validate` (company from the Project); no company hook | A Card Supervisor limited to company A inserts a draft review on a company-B project. |

In all four, Frappe checks the create right on the values the client sends (company still empty), and the
controller fills the company afterwards, as found for Card Monthly Card (D2) and Equipment Transport (D3) before
their `has_permission` hooks. The user cannot read the record afterwards.

## Other observations

- `card.api.refresh_supplier` / `refresh_customer`: gated by the System Manager role only. The registries have no
  company field and store no figures, so there is no company scope to apply.
- `card.tool_custody.item_query` reads Item with `ignore_permissions=True` after its screen-role gate (Items are
  global; the screen roles hold no Item DocPerm). Existing, documented in the function.
- `card.gl.posting.rebuild_month` / `post_month`: the builder inserts invoices with `ignore_permissions` after the
  endpoint's company gate (`_checked_endpoint_args`), which the tests cover.
- Number cards, the dashboard chart source and the Autocomplete sources accept POST although they only read,
  because the Frappe widgets post; their no-write tests cover them like the GET endpoints.
