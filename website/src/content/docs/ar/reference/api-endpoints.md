---
title: "نقاط الـ API"
description: "كل دوال الـ API المسموح باستدعائها في CARD مع طرق HTTP والمعاملات."
editUrl: false
sidebar:
  order: 3
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

| الوحدة | نقاط الـ API |
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

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.api.party_figures` | GET | `party_type: str`<br/>`party: str` |
| `card.api.refresh_supplier` | POST | `supplier: str \| None = None` |
| `card.api.card_suppliers_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.api.refresh_customer` | POST | `customer: str \| None = None` |
| `card.api.card_customers_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.api.card_project_options` | GET, POST | `txt: str \| None = None`<br/>`company: str \| None = None` |
| `card.api.report_defaults` | GET | لا يوجد |
| `card.api.card_company_options` | GET, POST | `txt: str \| None = None` |
| `card.api.get_only_company` | GET | لا يوجد |
| `card.api.get_asset_prefill` | GET | `asset: str` |
| `card.api.create_equipment_from_asset` | POST | `asset: str`<br/>`ownership: str = 'ملك'`<br/>`save: int \| str = 0` |
| `card.api.available_assets_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |


<h2 id="card-cancel-reason"><code>card.cancel_reason</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.cancel_reason.cancel_with_reason` | POST | `doctype: str`<br/>`name: str`<br/>`reason: str \| None = None` |


<h2 id="card-card-dashboard-chart-source-card-monthly-values-card-monthly-values"><code>card.card.dashboard_chart_source.card_monthly_values.card_monthly_values</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get` | POST | `chart_name: str \| None = None`<br/>`chart: str \| dict \| None = None`<br/>`no_cache: bool \| int \| str \| None = None`<br/>`filters: str \| dict \| list \| None = None`<br/>`from_date: str \| None = None`<br/>`to_date: str \| None = None`<br/>`timespan: str \| None = None`<br/>`time_interval: str \| None = None`<br/>`heatmap_year: str \| int \| None = None`<br/>`refresh: bool \| int \| str \| None = None` |


<h2 id="card-card-doctype-card-equipment-card-equipment"><code>card.card.doctype.card_equipment.card_equipment</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues` | GET | `company: str \| None = None` |
| `card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag` | POST | `equipment: str` |
| `card.card.doctype.card_equipment.card_equipment.get_shift_heatmap` | GET | `name: str` |
| `card.card.doctype.card_equipment.card_equipment.replace_component` | POST | `unit: str`<br/>`component: str`<br/>`new_component: str`<br/>`date: str`<br/>`reason: str \| None = None` |
| `card.card.doctype.card_equipment.card_equipment.move_component` | POST | `unit: str`<br/>`component: str`<br/>`target_unit: str`<br/>`date: str`<br/>`reason: str \| None = None` |


<h2 id="card-card-doctype-card-monthly-card-card-monthly-card"><code>card.card.doctype.card_monthly_card.card_monthly_card</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.card.doctype.card_monthly_card.card_monthly_card.get_card_context` | GET | `equipment: str`<br/>`month: str`<br/>`year: str`<br/>`project: str \| None = None` |


<h2 id="card-card-doctype-card-settings-card-settings"><code>card.card.doctype.card_settings.card_settings</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.card.doctype.card_settings.card_settings.getdoc` | GET, POST | `doctype: str`<br/>`name: str \| int` |
| `card.card.doctype.card_settings.card_settings.get_docinfo` | GET, POST | `doc: Document \| dict \| str \| None = None`<br/>`doctype: str \| None = None`<br/>`name: str \| int \| None = None` |


<h2 id="card-card-doctype-equipment-transport-equipment-transport"><code>card.card.doctype.equipment_transport.equipment_transport</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.card.doctype.equipment_transport.equipment_transport.get_equipment_location` | GET | `equipment: str` |
| `card.card.doctype.equipment_transport.equipment_transport.record_financial_decision` | POST | `transport: str`<br/>`decision: str`<br/>`customer: str \| None = None`<br/>`billing_project: str \| None = None`<br/>`billing_amount: float \| None = None`<br/>`billing_mode: str \| None = None`<br/>`billing_reference: str \| None = None`<br/>`billing_document: str \| None = None`<br/>`absorption_reason: str \| None = None`<br/>`recovery_mode: str \| None = None`<br/>`recovery_amount: float \| None = None`<br/>`note: str \| None = None`<br/>`confirmed: int \| str = 0` |
| `card.card.doctype.equipment_transport.equipment_transport.billing_customer` | GET | `transport: str`<br/>`project: str \| None = None` |


<h2 id="card-card-doctype-project-diesel-fill-project-diesel-fill"><code>card.card.doctype.project_diesel_fill.project_diesel_fill</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable` | GET | لا يوجد |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: str \| dict \| None = None` |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context` | GET | `company: str \| None = None`<br/>`date: str \| None = None` |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price` | POST | `name: str`<br/>`reason: str \| None = None` |
| `card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception` | POST | `name: str`<br/>`reason: str \| None = None` |


<h2 id="card-card-report-equipment-supplier-statement-statement-pdf"><code>card.card.report.equipment_supplier_statement.statement_pdf</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.card.report.equipment_supplier_statement.statement_pdf.download_pdf` | POST | `filters: str \| dict \| None = None` |


<h2 id="card-card-value"><code>card.card_value</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.card_value.supplier_cost_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.customer_value_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.internal_value_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.cards_without_internal_rate_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.hours_without_internal_rate_last_month` | POST | `filters: str \| dict \| list \| None = None` |
| `card.card_value.loads_last_month` | POST | `filters: str \| dict \| list \| None = None` |


<h2 id="card-catalog"><code>card.catalog</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.catalog.search` | GET | `txt: str \| None = None`<br/>`item_group: str \| None = None`<br/>`brand: str \| None = None`<br/>`start: int = 0`<br/>`page_length: int = PAGE_LENGTH`<br/>`equipment: str \| None = None`<br/>`fits: int = 0` |
| `card.catalog.filter_options` | GET | `kind: str`<br/>`txt: str \| None = None`<br/>`start: int = 0`<br/>`page_length: int = PAGE_LENGTH` |


<h2 id="card-daily-log-generation"><code>card.daily_log_generation</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.daily_log_generation.generate_monthly_cards` | POST | `company: str`<br/>`project: str`<br/>`month: str`<br/>`equipment: str \| None = None` |


<h2 id="card-diesel"><code>card.diesel</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.diesel.get_card_diesel` | GET | `card: str` |


<h2 id="card-diesel-reconciliation"><code>card.diesel_reconciliation</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.diesel_reconciliation.diesel_supplier_options` | GET | `txt: str \| None = None`<br/>`company: str \| None = None` |


<h2 id="card-fitment"><code>card.fitment</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.fitment.fit_for` | GET | `equipment: str`<br/>`items: str \| list` |
| `card.fitment.machines` | GET | `txt: str \| None = None`<br/>`start: int = 0` |


<h2 id="card-gl-integrity"><code>card.gl.integrity</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.gl.integrity.accept_correction` | POST | `invoice_doctype: str`<br/>`invoice: str`<br/>`reason: str` |
| `card.gl.integrity.link_supplier_invoice` | POST | `invoice: str`<br/>`sources: str \| list`<br/>`reason: str \| None = None`<br/>`accept_difference: int \| str = 0` |


<h2 id="card-gl-journal-link"><code>card.gl.journal_link</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.gl.journal_link.link_accrual_journal` | POST | `journal_entry: str`<br/>`cards: str \| list`<br/>`reason: str \| None = None`<br/>`accept_difference: int \| str = 0` |


<h2 id="card-gl-period-run"><code>card.gl.period_run</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.gl.period_run.build_run` | POST | `company: str`<br/>`month: str`<br/>`year: str` |
| `card.gl.period_run.period_run_status` | GET | `company: str`<br/>`month: str`<br/>`year: str` |


<h2 id="card-gl-posting"><code>card.gl.posting</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.gl.posting.rebuild_month` | POST | `company: str`<br/>`party_type: str`<br/>`party: str`<br/>`month: str`<br/>`year: str`<br/>`reviewed_invoices: str \| list \| None = None` |
| `card.gl.posting.post_month` | POST | `company: str`<br/>`party_type: str`<br/>`party: str`<br/>`month: str`<br/>`year: str`<br/>`reviewed_invoices: str \| list \| None = None` |
| `card.gl.posting.posting_month_parties` | GET | `company: str`<br/>`month: str`<br/>`year: str` |
| `card.gl.posting.preview_month` | GET | `company: str`<br/>`party_type: str`<br/>`party: str`<br/>`month: str`<br/>`year: str` |
| `card.gl.posting.posting_period_run` | GET | `company: str`<br/>`month: str`<br/>`year: str` |


<h2 id="card-governance-workflows"><code>card.governance_workflows</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.governance_workflows.return_for_correction` | POST | `doctype: str`<br/>`name: str`<br/>`reason: str \| None = None` |


<h2 id="card-materials"><code>card.materials</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.materials.review_stock` | GET | `review: str` |
| `card.materials.pull_requests` | POST | `review: str` |
| `card.materials.approve_review` | POST | `review: str` |
| `card.materials.close_tool_handover` | POST | `custody: str`<br/>`reason: str` |
| `card.materials.make_tool_handover` | POST | `review_item: str` |
| `card.materials.get_portal_context` | GET | لا يوجد |
| `card.materials.search_items` | GET | `txt: str \| None = None` |
| `card.materials.submit_needs` | POST | `equipment: str`<br/>`items: str \| list`<br/>`notes: str \| None = None` |


<h2 id="card-mobile"><code>card.mobile</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.mobile.get_session_context` | GET | لا يوجد |


<h2 id="card-tool-custody"><code>card.tool_custody</code></h2>

| مسار الدالة | طرق HTTP | المعاملات |
|---|---|---|
| `card.tool_custody.context` | GET | لا يوجد |
| `card.tool_custody.view` | GET | `tab: str = 'awaiting'`<br/>`employee: str \| None = None`<br/>`item_code: str \| None = None`<br/>`start: int = 0` |
| `card.tool_custody.employee_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.tool_custody.employee_company` | GET | `employee: str` |
| `card.tool_custody.store_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.tool_custody.item_query` | GET | `doctype: str`<br/>`txt: str`<br/>`searchfield: str`<br/>`start: int`<br/>`page_len: int`<br/>`filters: dict` |
| `card.tool_custody.confirm` | POST | `custody: str`<br/>`receipt: str \| None = None`<br/>`qty: float \| None = None`<br/>`serial_no: str \| None = None` |
| `card.tool_custody.move` | POST | `movement: str`<br/>`employee: str`<br/>`item_code: str`<br/>`qty: float`<br/>`to_employee: str \| None = None`<br/>`warehouse: str \| None = None`<br/>`serial_no: str \| None = None` |
