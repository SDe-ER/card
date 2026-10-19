// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// v4.0.0: the supervisor pulls the operators' requests of the project, records what is
// on site and what to approve, then submits; management approves into ERPNext.
frappe.ui.form.on("Equipment Needs Review", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Get requests"), () =>
				frappe
					.call({
						method: "card.materials.pull_requests",
						args: { review: frm.doc.name },
						freeze: true,
					})
					.then(() => frm.reload_doc()),
			);
		}
		const approver = frappe.user.has_role(["Card Manager", "System Manager"]);
		if (frm.doc.docstatus === 1 && frm.doc.approval_status === "Pending" && approver) {
			frm.add_custom_button(__("Approve"), () =>
				frappe.confirm(__("Create the Material Requests for the approved lines?"), () =>
					frappe
						.call({
							method: "card.materials.approve_review",
							args: { review: frm.doc.name },
							freeze: true,
						})
						.then(() => frm.reload_doc()),
				),
			).addClass("btn-primary");
		}
	},
});
