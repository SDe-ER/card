// Report: "Equipment Suppliers Summary" — filters + link to each supplier's statement
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

	frappe.query_reports["Equipment Suppliers Summary"] = {
		filters: [
			{
				fieldname: "from_month",
				label: __("من شهر"),
				fieldtype: "Select",
				options: months,
				default: pm,
				reqd: 1,
			},
			{ fieldname: "from_year", label: __("من سنة"), fieldtype: "Int", default: py, reqd: 1 },
			{
				fieldname: "to_month",
				label: __("إلى شهر"),
				fieldtype: "Select",
				options: months,
				default: pm,
				reqd: 1,
			},
			{ fieldname: "to_year", label: __("إلى سنة"), fieldtype: "Int", default: py, reqd: 1 },
			{ fieldname: "project", label: __("المشروع"), fieldtype: "Link", options: "Project" },
		],
		after_datatable_render: card_rtl_datatable,
		formatter(value, row, column, data, default_formatter) {
			value = default_formatter(value, row, column, data);
			if (!data) return value;
			if (data.is_total) return `<b>${value}</b>`;
			if (column.fieldname === "supplier_name" && data.supplier) {
				const f = frappe.query_report.get_filter_values();
				const q = new URLSearchParams({
					statement_type: "مورد",
					supplier: data.supplier,
					from_month: f.from_month,
					from_year: f.from_year,
					to_month: f.to_month,
					to_year: f.to_year,
				});
				if (f.project) q.set("project", f.project);
				return `<a href="/desk/query-report/Equipment Supplier Statement?${q.toString()}"><b>${value}</b></a>`;
			}
			if (column.fieldname === "diff" && Math.abs(data.diff || 0) >= 0.01) {
				return `<span style="color:var(--red-600)">${value}</span>`;
			}
			return value;
		},
	};
})();
