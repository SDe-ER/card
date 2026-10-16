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

	frappe.query_reports["Equipment Customer Statement"] = {
		filters: [
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
				get_query: () => ({ query: "card.api.card_companies_query" }),
			},
			{
				fieldname: "customer",
				label: __("Customer"),
				fieldtype: "Link",
				options: "Customer",
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
				fieldtype: "Link",
				options: "Project",
				get_query: () => ({
					query: "card.api.card_projects_query",
					filters: { company: frappe.query_report.get_filter_value("company") },
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
			// Seed the UI default from Card Settings (server also falls back to the
			// same setting for API callers). The user can still override.
			frappe.db
				.get_value("Card Settings", "Card Settings", ["include_draft_in_reports"])
				.then((r) => {
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
