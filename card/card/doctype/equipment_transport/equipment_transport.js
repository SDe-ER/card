// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// v3.0.0 (Owner 2026-10-19): the user picks ownership -> supplier -> the supplier's
// equipment -> project; the server reads the kind of move from each machine's history.
// The equipment link keeps frappe's own "Create a new Card Equipment" entry for a
// machine that is not registered yet.
frappe.ui.form.on("Equipment Transport", {
	setup(frm) {
		frm.set_query("card_equipment", "items", () => {
			const filters = { company: frm.doc.company || undefined };
			if (frm.doc.ownership) filters.ownership = frm.doc.ownership;
			if (frm.doc.equipment_supplier) filters.supplier = frm.doc.equipment_supplier;
			return { filters };
		});
	},
	onload(frm) {
		// one company only: fill it, the field stays editable
		if (frm.is_new() && !frm.doc.company) {
			frappe.call({ method: "card.api.get_only_company", type: "GET" }).then((r) => {
				if (r && r.message && !frm.doc.company) frm.set_value("company", r.message);
			});
		}
	},
	ownership(frm) {
		if (frm.doc.ownership === "ملك" && frm.doc.equipment_supplier) {
			frm.set_value("equipment_supplier", null);
		}
	},
});

// "From" is never typed: show where the machine is now as soon as it is picked
// (the server recomputes it on save from the last approved move).
frappe.ui.form.on("Equipment Transport Item", {
	card_equipment(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.card_equipment) return;
		frappe
			.call({
				method: "card.card.doctype.equipment_transport.equipment_transport.get_equipment_location",
				type: "GET",
				args: { equipment: row.card_equipment },
			})
			.then((r) => {
				const here = (r && r.message) || {};
				frappe.model.set_value(cdt, cdn, {
					from_type: here.type || "Storage",
					from_project: here.project || null,
					from_location: here.location || null,
				});
				// the header "From" follows the first machine
				if (row.idx === 1) {
					frm.set_value({
						source_type: here.type || "Storage",
						source_project: here.project || null,
						source_location: here.location || null,
					});
				}
			});
	},
});
