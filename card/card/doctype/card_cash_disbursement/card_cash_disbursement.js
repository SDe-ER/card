// FR-170 step 2: the Desk actions of a cash payment. Each button only calls a server method; the server checks the
// role, the company and the state again, so hiding a button is not the control.

frappe.ui.form.on("Card Cash Disbursement", {
	refresh(frm) {
		if (frm.is_new()) return;

		const act = (method, args, done) =>
			frappe.call({
				method,
				args,
				freeze: true,
				callback: () => {
					frm.reload_doc();
					frappe.show_alert({ message: done, indicator: "green" });
				},
			});

		if (frm.doc.status === "Pending") {
			frm.add_custom_button(__("Approve"), () =>
				frappe.confirm(__("Approve this cash payment? The approver must not be the requester."), () =>
					act("card.cash_disbursement.approve_cash_disbursement", { name: frm.doc.name }, __("Approved"))
				)
			);
		}

		if (frm.doc.status === "Approved") {
			frm.add_custom_button(__("Queue for posting"), () =>
				act("card.cash_disbursement.queue_posting", { name: frm.doc.name }, __("Queued for posting"))
			);
		}

		if (frm.doc.status === "Posted") {
			frm.add_custom_button(__("Request cancellation"), () =>
				frappe.prompt(
					{ label: __("Reason"), fieldname: "reason", fieldtype: "Small Text", reqd: 1 },
					(values) =>
						act(
							"card.cash_disbursement.request_cancellation",
							{ name: frm.doc.name, reason: values.reason },
							__("Cancellation requested")
						),
					__("Request cancellation"),
					__("Request")
				)
			);
		}
	},
});
