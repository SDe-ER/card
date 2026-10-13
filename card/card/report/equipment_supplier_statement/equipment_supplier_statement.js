// Report: "Equipment Supplier Statement" — filters + tree display
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

	frappe.query_reports["Equipment Supplier Statement"] = {
		filters: [
			{
				fieldname: "statement_type",
				label: "نوع الكشف",
				fieldtype: "Select",
				options: "مورد\nمعدات ملك",
				default: "مورد",
				reqd: 1,
			},
			{
				fieldname: "supplier",
				label: "المورد",
				fieldtype: "Link",
				options: "Supplier",
				depends_on: "eval:doc.statement_type=='مورد'",
			},
			{
				fieldname: "from_month",
				label: "من شهر",
				fieldtype: "Select",
				options: months,
				default: pm,
				reqd: 1,
			},
			{ fieldname: "from_year", label: "من سنة", fieldtype: "Int", default: py, reqd: 1 },
			{
				fieldname: "to_month",
				label: "إلى شهر",
				fieldtype: "Select",
				options: months,
				default: pm,
				reqd: 1,
			},
			{ fieldname: "to_year", label: "إلى سنة", fieldtype: "Int", default: py, reqd: 1 },
			{ fieldname: "project", label: "المشروع", fieldtype: "Link", options: "Project" },
			{
				fieldname: "equipment",
				label: "المعدة",
				fieldtype: "Link",
				options: "Card Equipment",
			},
			{
				fieldname: "equipment_type",
				label: "نوع المعدة",
				fieldtype: "Link",
				options: "Card Equipment Type",
			},
			{ fieldname: "include_draft", label: "تشمل المسودات", fieldtype: "Check", default: 0 },
		],
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
