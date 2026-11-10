// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// The approval names one customer-side addition row of the card. The server checks the row; the
// form only helps to choose it: one candidate is filled in, several are offered in a list.
frappe.ui.form.on("Card Owner Revenue Approval", {
	monthly_card(frm) {
		if (!frm.doc.monthly_card) return;
		frappe.db.get_doc("Card Monthly Card", frm.doc.monthly_card).then((card) => {
			const rows = (card.adjustments || []).filter(
				(row) => row.side === "Customer" && row.adjustment_type === "إضافة",
			);
			if (!rows.length) {
				frappe.msgprint(__("The card has no customer-side addition."));
				return;
			}
			const pick = (row) => {
				frm.set_value("adjustment_row", row.name);
				frm.set_value("description", row.description);
				frm.set_value("gross_amount", row.amount);
			};
			if (rows.length === 1) {
				pick(rows[0]);
				return;
			}
			frappe.prompt(
				{
					fieldname: "row",
					fieldtype: "Select",
					label: __("Card addition row"),
					options: rows.map((row) => ({
						value: row.name,
						label: `${row.description || ""} — ${format_currency(row.amount)}`,
					})),
					reqd: 1,
				},
				(values) => pick(rows.find((row) => row.name === values.row)),
				__("Card addition row"),
			);
		});
	},
});
