// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// F.1/F.3: company auto-fills from the user's default; the diesel supplier is
// read-only under the Fixed policy, and under Variable for users without the
// permitted role (the server enforces both — this only mirrors it in the form).
// Fill users cannot read Card Settings: the server answers yes/no for the supplier.
frappe.ui.form.on("Project Diesel Fill", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
		// one company only: fill it, the field stays editable
		if (frm.is_new() && !frm.doc.company) {
			frappe.call({ method: "card.api.get_only_company", type: "GET" }).then((r) => {
				if (r && r.message && !frm.doc.company) frm.set_value("company", r.message);
			});
		}
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frappe
			.call({
				method: "card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable",
				type: "GET",
			})
			.then((r) => frm.set_df_property("supplier", "read_only", r && r.message ? 0 : 1));
	},
});
