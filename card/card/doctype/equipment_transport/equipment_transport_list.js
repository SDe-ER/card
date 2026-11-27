// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// The list view draws a Select cell with the plain __(value) (form/formatters.js: Select), so "Workshop"
// would read without the DocType context its Arabic CARD translation sits under. A list-view formatter
// replaces that cell (list/list_view.js: `settings.formatters[fieldname](value, df, doc)`).
const workshop_cell = (value) => (value ? __(value, null, "Equipment Transport") : "");

frappe.listview_settings["Equipment Transport"] = {
	formatters: {
		destination_type: workshop_cell,
		source_type: workshop_cell,
	},
};
