// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// R1: equipment and project choices follow the employee's company.

frappe.ui.form.on("Card Personnel Assignment", {
	setup(frm) {
		const by_company = () => ({ filters: { company: frm.doc.company || "" } });
		frm.set_query("card_equipment", by_company);
		frm.set_query("project", by_company);
		frm.set_query("cost_center", () => ({
			filters: { company: frm.doc.company || "", is_group: 0, disabled: 0 },
		}));
	},
	employee(frm) {
		if (!frm.doc.employee) return;
		frappe.db.get_value("Employee", frm.doc.employee, "company").then((r) => {
			frm.set_value("company", (r && r.message && r.message.company) || "");
		});
	},
});
