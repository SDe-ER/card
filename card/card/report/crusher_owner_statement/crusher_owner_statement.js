// Report: "Crusher Owner Statement" — what each third-party equipment owner is due (read-only)
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

	frappe.query_reports["Crusher Owner Statement"] = {
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
				fieldname: "owner",
				label: __("Owner"),
				fieldtype: "Link",
				options: "Card Equipment Supplier",
				get_query: () => ({
					query: "card.api.card_suppliers_query",
					filters: { company: frappe.query_report.get_filter_value("company") },
				}),
			},
			{
				fieldname: "family",
				label: __("Family settlement group"),
				fieldtype: "Link",
				options: "Supplier Group",
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
				fieldname: "equipment",
				label: __("Equipment"),
				fieldtype: "Link",
				options: "Card Equipment",
			},
			{
				fieldname: "owner_model",
				label: __("Owner model"),
				fieldtype: "Select",
				options: ["", "Managed partner", "Self-operating owner"].join("\n"),
			},
		],
		onload(report) {
			// the PDF action prints the A4 statement with the Chrome PDF generator (Arabic shaping): the
			// server runs the report and builds the page from the filters only
			if (!report.card_owner_statement_pdf) {
				const standard_pdf = report.pdf_report;
				report.pdf_report = function (print_settings) {
					if (this.report_name !== "Crusher Owner Statement") {
						return standard_pdf.call(this, print_settings);
					}
					const filters = this.get_filter_values(true);
					if (!filters) return;
					open_url_post(
						"/api/method/card.card.report.crusher_owner_statement.owner_statement_pdf.download_pdf",
						{ filters },
						true,
					);
				};
				report.card_owner_statement_pdf = true;
			}
		},
		tree: true,
		name_field: "row_id",
		parent_field: "parent_row",
		initial_depth: 2,
		formatter(value, row, column, data, default_formatter) {
			value = default_formatter(value, row, column, data);
			if (data && data.bold) value = `<b>${value}</b>`;
			return value;
		},
	};
})();
