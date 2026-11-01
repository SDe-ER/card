// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// FR-100: a service order; the plan kit fills the parts of a new order.

frappe.ui.form.on("Card Maintenance Order", {
	equipment(frm) {
		if (!frm.doc.equipment || frm.doc.docstatus !== 0) return;
		frappe
			.call({
				method: "card.maintenance.get_plan_kit",
				args: { equipment: frm.doc.equipment },
				type: "GET",
			})
			.then((r) => {
				const d = (r && r.message) || {};
				frm.set_value("maintenance_plan", d.plan || "");
				if ((frm.doc.items || []).length || !(d.items || []).length) return;
				d.items.forEach((item) => {
					const row = frm.add_child("items");
					Object.assign(row, item, { from_kit: 1 });
				});
				frm.refresh_field("items");
			});
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		const make = (method, label) =>
			frm.add_custom_button(
				label,
				() =>
					frappe.call({ method, args: { order: frm.doc.name } }).then((r) => {
						if (r && r.message) frm.reload_doc();
					}),
				__("Create"),
			);
		if (!frm.doc.material_request && (frm.doc.items || []).length) {
			make("card.maintenance.make_material_request", __("Material Request"));
		}
		if (!frm.doc.purchase_invoice && (frm.doc.items || []).length) {
			make("card.maintenance.make_purchase_invoice", __("Purchase Invoice"));
		}
	},
});
