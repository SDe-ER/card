// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// FR-142: verify, approve or return a submitted daily log. The buttons only save approval_status (and the
// reason); the server (card.daily_log.check_transition) decides who may do it, whether the company asks for the
// supervisor step, and writes every approval field.

const PENDING = "Pending";
const VERIFIED = "Verified by supervisor";

frappe.ui.form.on("Card Daily Log", {
	refresh(frm) {
		const status = frm.doc.approval_status;
		if (frm.doc.docstatus !== 1 || ![PENDING, VERIFIED].includes(status)) return;
		const approver = frappe.user.has_role(["Card Manager", "System Manager"]);
		const supervisor = frappe.user.has_role("Card Supervisor");
		const set_status = (value) => {
			frm.set_value("approval_status", value);
			frm.save("Update");
		};
		if (supervisor && status === PENDING) {
			frm.add_custom_button(__("Verify daily log"), () => set_status(VERIFIED));
		}
		if (approver) {
			frm.add_custom_button(__("Approve daily log"), () => set_status("Approved"));
		}
		if (approver || (supervisor && status === PENDING)) {
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
						set_status("Returned for correction");
					},
					__("Return daily log"),
				);
			});
		}
	},
});
