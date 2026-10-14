// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// Mirrors Card Equipment Supplier's buttons for the customer registry.
frappe.ui.form.on("Card Equipment Customer", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Refresh numbers"), () => {
			frappe
				.call({
					method: "card.api.refresh_customer",
					args: { customer: frm.doc.customer },
					freeze: true,
					freeze_message: "جاري تحديث أرقام العميل...",
				})
				.then(() => frm.reload_doc());
		});

		frm.add_custom_button(__("Statement"), () => {
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
			frappe.set_route("query-report", "Equipment Customer Statement", {
				customer: frm.doc.customer,
				from_month: m,
				from_year: y,
				to_month: m,
				to_year: y,
			});
		}).addClass("btn-primary");
	},
});
