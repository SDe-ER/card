// Copyright (c) 2026, SDCE and contributors
// For license information, please see LICENSE

// FR-194 / FR-195: Desk buttons on a submitted customer Sales Invoice to link it to the CARD monthly cards it
// bills and to remove that link. The server decides everything: card.gl.integrity.customer_invoice_link_info
// (GET) gives the state and the candidate cards, link_customer_invoice and unlink_customer_invoice (POST) do the
// work and refuse what is not allowed. The buttons only follow the roles (Accounts Manager or System Manager to
// link; System Manager to remove). hooks.py loads this file for Sales Invoice.
if (!window.card_customer_invoice_link_registered) {
	window.card_customer_invoice_link_registered = true;

	const INFO = "card.gl.integrity.customer_invoice_link_info";
	const LINK = "card.gl.integrity.link_customer_invoice";
	const UNLINK = "card.gl.integrity.unlink_customer_invoice";
	const LINK_LABEL = __("Link to monthly cards");
	const UNLINK_LABEL = __("Remove link to monthly cards");

	const has_role = (role) => frappe.user.has_role(role);
	const esc = (text) => frappe.utils.escape_html(text == null ? "" : String(text));
	const money = (value, frm) => format_currency(value, frm.doc.currency);
	const card_text = (c, frm) =>
		`${esc(c.name)} - ${esc(c.month)}/${esc(c.year)} - ${esc(c.project)} - ${money(
			c.customer_net_amount,
			frm,
		)}`;

	const call_post = (frm, method, args, done_message) => {
		frappe.call({
			method,
			type: "POST",
			args,
			freeze: true,
			callback: (r) => {
				if (r.exc) return;
				frappe.show_alert({ message: done_message, indicator: "green" });
				frm.reload_doc();
			},
		});
	};

	const link_dialog = (frm, info) => {
		if (!info.cards.length) {
			frappe.msgprint(
				__(
					"This customer has no unlinked approved monthly card on the projects of this invoice.",
				),
			);
			return;
		}
		const cards = info.cards;
		const checks = cards.map((c, i) => ({
			fieldname: `card_${i}`,
			fieldtype: "Check",
			label: card_text(c, frm),
			change: () => update_totals(),
		}));
		const d = new frappe.ui.Dialog({
			title: LINK_LABEL,
			fields: [
				{ fieldname: "totals", fieldtype: "HTML" },
				...checks,
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Reason for linking this invoice"),
					reqd: 1,
				},
			],
			primary_action_label: __("Link the invoice"),
			primary_action(values) {
				const names = cards.filter((c, i) => values[`card_${i}`]).map((c) => c.name);
				if (!names.length) {
					frappe.msgprint(__("Choose the monthly cards this invoice bills."));
					return;
				}
				d.hide();
				call_post(
					frm,
					LINK,
					{ invoice: frm.doc.name, cards: JSON.stringify(names), reason: values.reason },
					__("The invoice is linked to the monthly cards."),
				);
			},
		});
		const update_totals = () => {
			const selected = cards.reduce(
				(sum, c, i) => sum + (d.get_value(`card_${i}`) ? c.customer_net_amount : 0),
				0,
			);
			d.get_field("totals").$wrapper.html(
				`<div>${__("Invoice net total")}: <b>${money(info.net_total, frm)}</b></div>` +
					`<div>${__("Selected cards total")}: <b>${money(selected, frm)}</b></div>`,
			);
		};
		d.show();
		update_totals();
	};

	const unlink_dialog = (frm, info) => {
		const d = new frappe.ui.Dialog({
			title: UNLINK_LABEL,
			fields: [
				{
					fieldname: "linked",
					fieldtype: "HTML",
					options: info.linked_cards
						.map((c) => `<div>${card_text(c, frm)}</div>`)
						.join(""),
				},
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: __("Reason for removing the link"),
					reqd: 1,
				},
			],
			primary_action_label: __("Remove the link"),
			primary_action(values) {
				d.hide();
				call_post(
					frm,
					UNLINK,
					{ invoice: frm.doc.name, reason: values.reason },
					__("The link to the monthly cards is removed."),
				);
			},
		});
		d.show();
	};

	const show_state = (frm, info) => {
		const group = __("CARD");
		frm.remove_custom_button(LINK_LABEL, group);
		frm.remove_custom_button(UNLINK_LABEL, group);
		if (info.linked) {
			frm.dashboard.set_headline_alert(
				__("Linked to monthly cards: {0}", [
					info.linked_cards.map((c) => esc(c.name)).join(", "),
				]),
				"blue",
			);
			if (info.origin === "Linked" && has_role("System Manager"))
				frm.add_custom_button(UNLINK_LABEL, () => unlink_dialog(frm, info), group);
		} else if (info.eligible) {
			frm.add_custom_button(LINK_LABEL, () => link_dialog(frm, info), group);
		}
	};

	frappe.ui.form.on("Sales Invoice", {
		refresh(frm) {
			if (frm.doc.docstatus !== 1 || frm.doc.is_return || frm.doc.is_debit_note) return;
			if (!has_role("Accounts Manager") && !has_role("System Manager")) return;
			const name = frm.doc.name;
			frappe.call({
				method: INFO,
				type: "GET",
				args: { invoice: name },
				callback: (r) => {
					if (r.message && frm.doc.name === name && frm.doc.docstatus === 1)
						show_state(frm, r.message);
				},
			});
		},
	});
}
