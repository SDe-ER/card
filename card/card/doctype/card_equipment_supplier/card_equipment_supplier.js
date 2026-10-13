// Copyright (c) 2026, Ahmed Shehab and contributors
// For license information, please see LICENSE
// Ported from Client Script "Card Equipment Supplier - Buttons".
// Button method updated for the app: card_supplier_refresh -> card.api.refresh_supplier.
frappe.ui.form.on("Card Equipment Supplier", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button("تحديث الأرقام", () => {
			frappe
				.call({
					method: "card.api.refresh_supplier",
					args: { supplier: frm.doc.supplier },
					freeze: true,
					freeze_message: "جاري تحديث أرقام المورد...",
				})
				.then(() => frm.reload_doc());
		});

		frm.add_custom_button("كشف الحساب", () => {
			// default period = last operating month on record, else previous calendar month
			let y, m;
			if (frm.doc.last_month) {
				y = parseInt(frm.doc.last_month.slice(0, 4));
				m = frm.doc.last_month.slice(5, 7);
			} else {
				const p = new Date(new Date().getFullYear(), new Date().getMonth() - 1, 1);
				y = p.getFullYear();
				m = String(p.getMonth() + 1).padStart(2, "0");
			}
			frappe.set_route("query-report", "Equipment Supplier Statement", {
				statement_type: "مورد",
				supplier: frm.doc.supplier,
				from_month: m,
				from_year: y,
				to_month: m,
				to_year: y,
			});
		}).addClass("btn-primary");
	},
});
