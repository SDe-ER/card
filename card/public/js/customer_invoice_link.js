// Copyright (c) 2026, SDCE and contributors
// For license information, please see LICENSE

// FR-194 / FR-195: Desk buttons on a submitted customer Sales Invoice to link it to the CARD monthly cards it
// bills and to remove that link. The server decides everything: card.gl.integrity.customer_invoice_link_info
// (GET) gives the state (on every refresh, without the card list) and the candidate cards (when the link dialog
// opens); link_customer_invoice and unlink_customer_invoice (POST) do the work and refuse what is not allowed.
// The buttons only follow the roles (Accounts Manager or System Manager to link; System Manager to remove) and
// the state the server reports. A refused state call shows nothing: no dialog, no button.
// hooks.py loads this file for Sales Invoice.
if (!window.card_customer_invoice_link_registered) {
	window.card_customer_invoice_link_registered = true;

	const INFO = "card.gl.integrity.customer_invoice_link_info";
	const LINK = "card.gl.integrity.link_customer_invoice";
	const UNLINK = "card.gl.integrity.unlink_customer_invoice";
	const LINK_LABEL = __("Link to monthly cards");
	const UNLINK_LABEL = __("Remove link to monthly cards");
	const HEADLINE_CARDS = 10;

	const has_role = (role) => frappe.user.has_role(role);
	const esc = (text) => frappe.utils.escape_html(text == null ? "" : String(text));
	const money = (value, frm) => format_currency(value, frm.doc.currency);
	const card_text = (c, frm) =>
		`${esc(c.name)} - ${esc(c.month)}/${esc(c.year)} - ${esc(c.project)} - ${money(
			c.customer_net_amount,
			frm,
		)}`;

	// the state call is quiet: a refusal (role, company, read right) must never open a dialog on a form refresh
	const read_info = (frm, args, callback) =>
		frappe.call({
			method: INFO,
			type: "GET",
			args: { invoice: frm.doc.name, ...args },
			freeze: false,
			silent: true,
			error_handlers: { PermissionError: () => {} },
			callback: (r) => r.message && callback(r.message),
		});

	// the dialog stays open until the server answers: the primary button is off while the call runs, the dialog
	// closes on success, and an error keeps it open with the server message
	const call_post = (frm, dialog, method, args, done_message) => {
		const button = dialog.get_primary_btn();
		button.prop("disabled", true);
		frappe.call({
			method,
			type: "POST",
			args,
			freeze: false,
			callback: (r) => {
				if (r.exc) return button.prop("disabled", false);
				dialog.hide();
				frappe.show_alert({ message: done_message, indicator: "green" });
				frm.reload_doc();
			},
			error: () => button.prop("disabled", false),
		});
	};

	const link_dialog = (frm, info) => {
		const cards = info.cards;
		if (!cards.length) {
			frappe.msgprint(
				__(
					"This customer has no unlinked approved monthly card on the projects of this invoice.",
				),
			);
			return;
		}
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
				call_post(
					frm,
					d,
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
			const more = info.more_cards
				? `<div class="text-muted">${esc(
						__("Showing the newest {0} of {1} monthly cards", [
							cards.length,
							info.card_count,
						]),
				  )}</div>`
				: "";
			d.get_field("totals").$wrapper.html(
				`<div>${__("Invoice net total")}: <b>${money(info.net_total, frm)}</b></div>` +
					`<div>${__("Selected cards total")}: <b>${money(selected, frm)}</b></div>` +
					more,
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
				call_post(
					frm,
					d,
					UNLINK,
					{ invoice: frm.doc.name, reason: values.reason },
					__("The link to the monthly cards is removed."),
				);
			},
		});
		d.show();
	};

	// one extra block under the other headlines of the form (set_headline_alert appends, it never replaces);
	// the block of an earlier refresh is removed first
	const show_headline = (frm, info) => {
		frm.layout.message.find("[data-card-invoice-link]").remove();
		const names = info.linked_cards.map((c) => esc(c.name));
		const shown = names.slice(0, HEADLINE_CARDS).join(", ");
		const rest = names.length - HEADLINE_CARDS;
		const text =
			rest > 0
				? __("Linked to monthly cards: {0} and {1} more", [shown, rest])
				: __("Linked to monthly cards: {0}", [shown]);
		frm.dashboard.set_headline_alert(text, "blue");
		frm.layout.message.find(".form-message").last().attr("data-card-invoice-link", "1");
	};

	const show_state = (frm, info) => {
		const group = __("CARD");
		frm.remove_custom_button(LINK_LABEL, group);
		frm.remove_custom_button(UNLINK_LABEL, group);
		if (info.linked) {
			// a user who cannot read the cards sees neither the headline nor the button
			if (!info.linked_cards.length) return;
			show_headline(frm, info);
			if (info.origin === "Linked" && has_role("System Manager"))
				frm.add_custom_button(UNLINK_LABEL, () => unlink_dialog(frm, info), group);
		} else if (info.eligible && info.card_count > 0) {
			frm.add_custom_button(
				LINK_LABEL,
				() => read_cards_then(frm, (full) => link_dialog(frm, full)),
				group,
			);
		}
	};

	// the candidate cards are read when the dialog opens, not on every refresh
	const read_cards_then = (frm, callback) =>
		frappe.call({
			method: INFO,
			type: "GET",
			args: { invoice: frm.doc.name, with_cards: 1 },
			callback: (r) => r.message && callback(r.message),
		});

	frappe.ui.form.on("Sales Invoice", {
		refresh(frm) {
			if (frm.doc.docstatus !== 1 || frm.doc.is_return || frm.doc.is_debit_note) return;
			if (!has_role("Accounts Manager") && !has_role("System Manager")) return;
			const name = frm.doc.name;
			read_info(frm, {}, (info) => {
				if (frm.doc.name === name && frm.doc.docstatus === 1) show_state(frm, info);
			});
		},
	});
}
