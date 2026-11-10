// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// FR-142: approve or return a submitted daily log. The buttons only save approval_status (and the reason);
// the server (card.daily_log.check_transition) decides who may do it and writes every approval field.

frappe.ui.form.on("Card Daily Log", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.approval_status !== "Pending") return;
		if (!frappe.user.has_role(["Card Manager", "System Manager"])) return;
		frm.add_custom_button(__("Approve daily log"), () => {
			frm.set_value("approval_status", "Approved");
			frm.save("Update");
		});
		frm.add_custom_button(__("Return daily log"), () => {
			frappe.prompt(
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Daily log return reason"),
					reqd: 1,
				},
				(values) => {
					frm.set_value("return_reason", values.reason);
					frm.set_value("approval_status", "Returned");
					frm.save("Update");
				},
				__("Return daily log"),
			);
		});
	},
});
