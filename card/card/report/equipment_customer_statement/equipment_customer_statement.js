// Report: "Equipment Customer Statement" — filters + tree display
(function () {
	const now = new Date();
	const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
	const pm = String(prev.getMonth() + 1).padStart(2, "0");
	const py = prev.getFullYear();
	const months = [
		"",
		"01",
		"02",
		"03",
		"04",
		"05",
		"06",
		"07",
		"08",
		"09",
		"10",
		"11",
		"12",
	].join("\n");

	// v1.2: RTL datatable fix. an Arabic print style sets .dt-scrollable{direction:rtl} (body) but not the header,
	// and frappe-datatable syncs the header with translateX(-scrollLeft), which is invalid for negative RTL scrollLeft.
	function card_rtl_datatable(dt) {
		if (!document.getElementById("card-rtl-dt-header")) {
			const s = document.createElement("style");
			s.id = "card-rtl-dt-header";
			s.textContent = ".datatable .dt-header { direction: rtl; }";
			document.head.appendChild(s);
		}
		const wrap = dt && dt.wrapper;
		const sc = wrap && wrap.querySelector(".dt-scrollable");
		const hdr = wrap && wrap.querySelector(".dt-header");
		if (!sc || !hdr || sc._card_rtl) return;
		sc._card_rtl = true;
		const sync = () => {
			hdr.style.transform = `translateX(${-sc.scrollLeft}px)`;
		};
		sc.addEventListener("scroll", sync);
		sync();
	}

	// frappe 16.60: the PDF button of the report print page (frappe.views.ReportPrintView.download_pdf) does not call
	// report.pdf_report. For a tree report it sends the browser's HTML to wkhtmltopdf, which breaks Arabic letter
	// joins (issue 324). The button of this statement goes to the same server route as report.pdf_report; every
	// other report keeps the standard button. The class is loaded with the print page, after this script, so the
	// patch is applied in the capture phase of a click: before the handler of the button runs.
	function card_statement_print_page_pdf(report_name, method) {
		frappe.card_statement_pdf_routes = frappe.card_statement_pdf_routes || {};
		frappe.card_statement_pdf_routes[report_name] = method;
		if (frappe.card_statement_pdf_listener) return;
		const patch = () => {
			const View = frappe.views.ReportPrintView;
			if (!View || !View.prototype.download_pdf || View.prototype.card_statement_pdf) return;
			const standard = View.prototype.download_pdf;
			View.prototype.download_pdf = function () {
				const route = frappe.card_statement_pdf_routes[this.report && this.report.report_name];
				if (!route) return standard.call(this);
				// required filters are checked here, like the report run; the page is a fixed A4 statement
				const filters = this.report.get_filter_values(true);
				if (!filters) return;
				open_url_post(`/api/method/${route}`, { filters }, true);
			};
			View.prototype.card_statement_pdf = true;
		};
		document.addEventListener("click", patch, true);
		frappe.card_statement_pdf_listener = true;
	}

	frappe.query_reports["Equipment Customer Statement"] = {
		filters: [
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Autocomplete",
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
				get_query: () => ({ query: "card.api.card_company_options" }),
			},
			{
				fieldname: "customer",
				label: __("Customer"),
				fieldtype: "Link",
				options: "Card Equipment Customer",
				get_query: () => ({
					query: "card.api.card_customers_query",
					filters: { company: frappe.query_report.get_filter_value("company") },
				}),
			},
			{
				fieldname: "from_month",
				label: __("From month"),
				fieldtype: "Select",
				options: months,
				default: pm,
				reqd: 1,
			},
			{
				fieldname: "from_year",
				label: __("From year"),
				fieldtype: "Int",
				default: py,
				reqd: 1,
			},
			{
				fieldname: "to_month",
				label: __("To month"),
				fieldtype: "Select",
				options: months,
				default: pm,
				reqd: 1,
			},
			{ fieldname: "to_year", label: __("To year"), fieldtype: "Int", default: py, reqd: 1 },
			{
				fieldname: "project",
				label: __("Project"),
				fieldtype: "Autocomplete",
				get_query: () => ({
					query: "card.api.card_project_options",
					params: { company: frappe.query_report.get_filter_value("company") },
				}),
			},
			{
				fieldname: "equipment",
				label: __("Equipment"),
				fieldtype: "Link",
				options: "Card Equipment",
			},
			{
				fieldname: "equipment_type",
				label: __("Equipment type"),
				fieldtype: "Link",
				options: "Card Equipment Type",
			},
			{ fieldname: "include_draft", label: __("Include drafts"), fieldtype: "Check" },
		],
		onload(report) {
			// the PDF dialog opens with the A4 statement selected; the Print dialog uses the same layout
			report.report_doc.default_print_format = "Equipment Customer Statement A4";
			// the PDF action prints this statement with the Chrome PDF generator (Arabic shaping, issue #324): the
			// server runs the report and builds the page from the filters only. Other reports keep the standard PDF.
			if (!report.card_customer_statement_pdf) {
				const standard_pdf = report.pdf_report;
				report.pdf_report = function (print_settings) {
					if (this.report_name !== "Equipment Customer Statement") {
						return standard_pdf.call(this, print_settings);
					}
					// required filters are checked here, like the report run; the page is a fixed A4 statement
					const filters = this.get_filter_values(true);
					if (!filters) return;
					open_url_post(
						"/api/method/card.card.report.equipment_customer_statement.statement_pdf.download_pdf",
						{ filters },
						true,
					);
				};
				report.card_customer_statement_pdf = true;
			}
			// the PDF button of the report print page (frappe 16.60) goes to the same server route
			card_statement_print_page_pdf(
				"Equipment Customer Statement",
				"card.card.report.equipment_customer_statement.statement_pdf.download_pdf",
			);
			// Seed the UI default from Card Settings (server also falls back to the
			// same setting for API callers). The user can still override.
			frappe.call({ method: "card.api.report_defaults", type: "GET" }).then((r) => {
				const v = (r && r.message) || {};
				const idf = report.get_filter("include_draft");
				if (idf) idf.set_value(v.include_draft_in_reports ? 1 : 0);
			});
		},
		tree: true,
		name_field: "row_id",
		parent_field: "parent_row",
		initial_depth: 1,
		after_datatable_render: card_rtl_datatable,
		formatter(value, row, column, data, default_formatter) {
			value = default_formatter(value, row, column, data);
			if (data && data.bold) value = `<b>${value}</b>`;
			if (data && data.row_id === "TOTAL")
				value = `<span style="color:var(--green-700)">${value}</span>`;
			return value;
		},
	};
})();
