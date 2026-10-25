// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// v4.0.0: the supervisor pulls the operators' requests of the project, records what is
// on site and what to approve, then submits; management approves into ERPNext.
frappe.ui.form.on("Equipment Needs Review", {
	refresh(frm) {
		card_show_review_stock(frm);
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
			frm.add_custom_button(__("Approve", null, "Card"), () =>
				frappe.confirm(
					__("Approve the lines? Tools wait for the store to hand them over."),
					() =>
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

// The stock hint is not stored (F2): it is read live with the reader's own ERPNext rights and
// shown only to a user who may read stock.
function card_show_review_stock(frm) {
	const grid = frm.fields_dict.items.grid;
	grid.update_docfield_property("stock_qty", "hidden", 1);
	if (frm.is_new() || !(frm.doc.items || []).length) return;
	const review = frm.doc.name;
	frappe
		.call({
			method: "card.materials.review_stock",
			args: { review: frm.doc.name },
			type: "GET",
		})
		.then((r) => {
			const stock = r.message || {};
			// the form may show another review by now
			if (frm.doc.name !== review || !Object.keys(stock).length) return;
			(frm.doc.items || []).forEach((row) => {
				// no hint (no item, or a warehouse the reader may not see) stays empty, not 0
				row.stock_qty = stock[row.name] ?? null;
			});
			grid.update_docfield_property("stock_qty", "hidden", 0);
			frm.refresh_field("items");
		});
}
