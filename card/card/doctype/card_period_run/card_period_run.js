// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// FR-147: approve or return a submitted period run, and show whether its cards changed since it was built. The
// buttons only save approval_status (and the reason); the server (card.gl.period_run.check_transition) decides
// who may do it, refuses a stale run and writes every approval field.

frappe.ui.form.on("Card Period Run", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus === 2) return;
		frappe
			.call({
				method: "card.gl.period_run.period_run_status",
				type: "GET",
				args: { company: frm.doc.company, month: frm.doc.month, year: frm.doc.year },
			})
			.then((r) => {
				const state = r.message || {};
				if (state.run !== frm.doc.name) return;
				if (state.current) {
					frm.dashboard.set_headline_alert(
						__("The cards of this period run are unchanged since it was built."),
						"green",
					);
				} else {
					frm.dashboard.set_headline_alert(
						__(
							"The cards of this period run changed after it was built; cancel and amend it to build a new version.",
						),
						"orange",
					);
				}
			});
		if (frm.doc.docstatus !== 1 || frm.doc.approval_status !== "Pending") return;
		if (!frappe.user.has_role(["Accounts Manager", "System Manager"])) return;
		const set_status = (value) => {
			frm.set_value("approval_status", value);
			frm.save("Update");
		};
		frm.add_custom_button(__("Approve period run"), () => set_status("Approved"));
		frm.add_custom_button(__("Return period run"), () => {
			frappe.prompt(
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Period run return reason"),
					reqd: 1,
				},
				(values) => {
					frm.set_value("return_reason", values.reason);
					set_status("Returned for correction");
				},
				__("Return period run"),
			);
		});
	},
});
