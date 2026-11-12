// Copyright (c) 2026, SDCE and contributors
// For license information, please see LICENSE

// FR-123 (WP-07, governance G0): a CARD transaction is cancelled only with a reason. The form's
// Cancel asks for the reason, then card.cancel_reason.cancel_with_reason stores it and cancels in
// one request (a refused cancel keeps no reason); the standard cancel request is not sent. The
// server refuses every cancel without a reason (REST and API included).
// hooks.py loads this file for the three doctypes; the handlers are registered once.
if (!window.card_cancel_reason_registered) {
	window.card_cancel_reason_registered = true;

	const ask_cancel_reason = (frm) =>
		new Promise((resolve) => {
			let reason = null;
			const d = new frappe.ui.Dialog({
				title: __("Cancel Reason"),
				fields: [
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("Cancel Reason"),
						reqd: 1,
					},
				],
				primary_action_label: __("Cancel with this reason"),
				primary_action(values) {
					const text = (values.reason || "").trim();
					if (!text) {
						frappe.msgprint(
							__("A cancel reason is required to cancel {0} {1}.", [
								__(frm.doctype),
								frm.docname,
							]),
						);
						return;
					}
					reason = text;
					d.hide();
				},
			});
			d.onhide = () => resolve(reason);
			d.show();
		});

	const before_cancel = async (frm) => {
		const reason = await ask_cancel_reason(frm);
		// the standard cancel request never runs; the server method cancels with the reason
		frappe.validated = false;
		if (!reason) return;
		try {
			await frappe.call({
				method: "card.cancel_reason.cancel_with_reason",
				type: "POST",
				args: { doctype: frm.doctype, name: frm.docname, reason },
				freeze: true,
			});
			frappe.show_alert({
				message: __("Cancelled with the reason recorded."),
				indicator: "red",
			});
		} catch (e) {
			// refused on the server: frappe already shows the server's message
		}
		await frm.reload_doc();
		// set again after the awaits: another handler or the reload may have reset it
		frappe.validated = false;
	};

	// FR-152: the workflow action "Return for Correction" asks for its mandatory reason, then
	// card.governance_workflows.return_for_correction applies the action with it in one request; the
	// standard apply_workflow request is not sent (the server refuses a return without the reason).
	const RETURN_ACTION = "Return for Correction";
	const ask_return_reason = () =>
		new Promise((resolve) => {
			let reason = null;
			const d = new frappe.ui.Dialog({
				title: __("Return for Correction"),
				fields: [
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("Return for correction reason"),
						reqd: 1,
					},
				],
				primary_action_label: __("Return with this reason"),
				primary_action(values) {
					const text = (values.reason || "").trim();
					if (!text) return;
					reason = text;
					d.hide();
				},
			});
			d.onhide = () => resolve(reason);
			d.show();
		});

	const before_workflow_action = async (frm) => {
		if (frm.selected_workflow_action !== RETURN_ACTION) return;
		frappe.dom.unfreeze();
		const reason = await ask_return_reason();
		if (reason) {
			try {
				await frappe.call({
					method: "card.governance_workflows.return_for_correction",
					type: "POST",
					args: { doctype: frm.doctype, name: frm.docname, reason },
					freeze: true,
				});
			} catch (e) {
				// refused on the server: frappe already shows the server's message
			}
			await frm.reload_doc();
		}
		frm.selected_workflow_action = null;
		// never resolves: the standard apply_workflow request must not run after this handler
		return new Promise(() => {});
	};

	for (const doctype of ["Card Monthly Card", "Equipment Transport", "Project Diesel Fill"]) {
		frappe.ui.form.on(doctype, { before_cancel, before_workflow_action });
	}
}
