// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// FR-141 (#41): pickers follow the agreement's company and equipment type (the server enforces both).
frappe.ui.form.on("Card Rate Agreement", {
	setup(frm) {
		frm.set_query("equipment", () => ({ filters: { company: frm.doc.company || "" } }));
		frm.set_query("project", () => ({ filters: { company: frm.doc.company || "" } }));
		frm.set_query("equipment", "responsibilities", () => {
			const filters = { company: frm.doc.company || "" };
			if (frm.doc.equipment) filters.name = frm.doc.equipment;
			else if (frm.doc.equipment_type) filters.equipment_type = frm.doc.equipment_type;
			return { filters };
		});
	},
});
