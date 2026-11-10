// Report: "Equipment Downtime" — read-only; stopped days and hours of the monthly cards by reason (FR-118, #45)
frappe.query_reports["Equipment Downtime"] = {
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
			fieldname: "from_date",
			label: __("From date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "group_by",
			label: __("Group downtime by"),
			fieldtype: "Select",
			options: [
				{ value: "Reason", label: __("Stop reason") },
				{ value: "Responsible party", label: __("Responsible party") },
				{ value: "Equipment", label: __("Equipment") },
				{ value: "Project", label: __("Project") },
				{ value: "Month", label: __("Month") },
				{ value: "Detail", label: __("Each day") },
			],
			default: "Reason",
		},
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
			fieldname: "stop_reason",
			label: __("Stop reason"),
			fieldtype: "Link",
			options: "Card Stop Reason",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") || "" },
			}),
		},
		{
			fieldname: "responsible_party_type",
			label: __("Responsible party"),
			fieldtype: "Select",
			options: [
				{ value: "", label: "" },
				{ value: "Company", label: __("Company") },
				{ value: "Supplier", label: __("Supplier") },
				{ value: "Customer", label: __("Customer") },
				{ value: "Other", label: __("Other") },
			],
		},
		{
			fieldname: "include_drafts",
			label: __("Include draft cards"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
