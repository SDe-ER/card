// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

frappe.ui.form.on("Card Equipment", {
	refresh(frm) {
		if (frm.is_new()) return;
		const group = __("الارتباطات");

		// Current lessor (the supplier stored on this equipment).
		if (frm.doc.supplier) {
			frm.add_custom_button(
				__("المورد الحالي"),
				() => frappe.set_route("Form", "Supplier", frm.doc.supplier),
				group,
			);
		}

		// Suppliers that billed this equipment — shown via its monthly cards
		// (each card carries its supplier), across every period.
		frm.add_custom_button(
			__("الموردين"),
			() => frappe.set_route("List", "Card Monthly Card", { equipment: frm.doc.name }),
			group,
		);

		// Projects this equipment worked on — its assignments (equipment ↔ project).
		frm.add_custom_button(
			__("المشاريع"),
			() => frappe.set_route("List", "Card Equipment Assignment", { equipment: frm.doc.name }),
			group,
		);
	},
});
