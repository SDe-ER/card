// FR-170: the Desk actions and statuses of a cash payment. Each button only calls a server method; the server checks
// the role, the company and the state again, so hiding a button is not the control. The posting status and the
// reconciliation status are shown as two separate indicators.

const CCD_POSTING_INDICATORS = {
	Pending: [__("Pending approval"), "orange"],
	Approved: [__("Approved"), "blue"],
	Posting: [__("Queued for posting"), "blue"],
	"Posting Failed": [__("Posting failed"), "red"],
	Posted: [__("Posted"), "green"],
	"Cancellation Requested": [__("Cancellation requested"), "orange"],
	Cancelled: [__("Cancelled"), "darkgrey"],
};
const CCD_RECONCILIATION_INDICATORS = {
	Unreconciled: [__("Not reconciled"), "orange"],
	"Partially reconciled": [__("Partially reconciled"), "blue"],
	"Fully reconciled": [__("Fully reconciled"), "green"],
};

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

		const posting = CCD_POSTING_INDICATORS[frm.doc.status];
		if (posting) frm.dashboard.add_indicator(posting[0], posting[1]);

		if (frm.doc.status === "Posted" && frm.doc.card) {
			frappe.call({
				method: "card.cash_disbursement.get_cash_disbursements",
				type: "GET", // GET-only endpoint; a default POST is refused with "Not permitted"
				args: { card: frm.doc.card },
				callback: (r) => {
					const mine = (r.message || []).find((row) => row.name === frm.doc.name);
					const recon = mine && CCD_RECONCILIATION_INDICATORS[mine.reconciliation];
					if (recon) frm.dashboard.add_indicator(recon[0], recon[1]);
				},
			});
		}

		if (frm.doc.status === "Pending") {
			frm.add_custom_button(__("Approve"), () =>
				frappe.confirm(
					__("Approve this cash payment? The approver must not be the requester."),
					() =>
						act(
							"card.cash_disbursement.approve_cash_disbursement",
							{ name: frm.doc.name },
							__("Approved"),
						),
				),
			);
		}

		if (frm.doc.status === "Approved") {
			frm.add_custom_button(__("Queue for posting"), () =>
				act(
					"card.cash_disbursement.queue_posting",
					{ name: frm.doc.name },
					__("Queued for posting"),
				),
			);
		}

		if (frm.doc.status === "Posting Failed") {
			frm.add_custom_button(__("Retry posting"), () =>
				act(
					"card.cash_disbursement.queue_posting",
					{ name: frm.doc.name },
					__("Queued for posting"),
				),
			);
		}

		const never_posted =
			["Approved", "Posting Failed"].includes(frm.doc.status) && !frm.doc.journal_entry;
		if (frm.doc.status === "Posted" || never_posted) {
			frm.add_custom_button(__("Request cancellation"), () =>
				frappe.prompt(
					{ label: __("Reason"), fieldname: "reason", fieldtype: "Small Text", reqd: 1 },
					(values) =>
						act(
							"card.cash_disbursement.request_cancellation",
							{ name: frm.doc.name, reason: values.reason },
							__("Cancellation requested"),
						),
					__("Request cancellation"),
					__("Request"),
				),
			);
		}

		// A replacement is a new Pending payment with its own approval by a different Card Manager. Clicking this creates
		// no accounting entry; the server refuses a second live replacement for the same cancelled payment.
		// Shown to Card Managers only (the server enforces the same rule). The dialog stays open when the server refuses,
		// so the typed reason and evidence are kept: frappe.prompt would hide the dialog before the server answers.
		if (frm.doc.status === "Cancelled" && frappe.user.has_role("Card Manager")) {
			frm.add_custom_button(__("Request replacement"), () => {
				const dialog = new frappe.ui.Dialog({
					title: __("Request replacement"),
					fields: [
						{
							label: __("Reason"),
							fieldname: "reason",
							fieldtype: "Small Text",
							reqd: 1,
						},
						{
							label: __("Payment date"),
							fieldname: "payment_date",
							fieldtype: "Date",
							reqd: 1,
							default: frappe.datetime.get_today(),
						},
						{
							label: __("Evidence (receipt number or reference)"),
							fieldname: "evidence",
							fieldtype: "Small Text",
							reqd: 1,
						},
					],
					primary_action_label: __("Request"),
					primary_action: (values) =>
						frappe.call({
							method: "card.cash_disbursement.request_replacement",
							args: {
								name: frm.doc.name,
								reason: values.reason,
								payment_date: values.payment_date,
								evidence: values.evidence,
							},
							freeze: true,
							callback: (r) => {
								dialog.hide();
								frappe.show_alert({
									message: __("Replacement requested: {0}", [r.message]),
									indicator: "green",
								});
								frappe.set_route("Form", "Card Cash Disbursement", r.message);
							},
						}),
				});
				dialog.show();
			});
		}
	},
});
