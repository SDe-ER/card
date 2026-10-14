// Report: "Operating Cost by Project" — filters
frappe.query_reports["Operating Cost by Project"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_default("company"),
		},
		{ fieldname: "from_date", label: __("From date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To date"), fieldtype: "Date" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
	],
};
