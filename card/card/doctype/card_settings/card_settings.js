// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// Owner 2026-10-20: the diesel price per litre shows on top of Diesel Settings as one clear value.
// Its only source stays Card Company Settings.diesel_unit_price (one row per company); editing it
// needs write on that field's permlevel, which the server enforces on save.
const CARD_ADVANCED_ROLES = [
	"diesel_supplier_editor_role",
	"diesel_price_exception_role",
	"diesel_zero_price_role",
	"transport_price_editor_role",
];

function card_can(frm, permlevel, ptype) {
	return !!(frm.perm && frm.perm[permlevel] && frm.perm[permlevel][ptype]);
}

function card_can_write(frm, permlevel) {
	return card_can(frm, permlevel, "write");
}

function card_price_rows(frm) {
	const rows = (frm.doc.company_settings || []).filter((r) => r.company);
	const allowed = ((frappe.defaults.get_user_permissions() || {}).Company || []).map(
		(p) => p.doc,
	);
	return allowed.length ? rows.filter((r) => allowed.includes(r.company)) : rows;
}

function card_render_diesel_price(frm) {
	const field = frm.get_field("diesel_price_html");
	if (!field) return;
	// the price is a permlevel-1 field: users who cannot read it do not get it from the server
	frm.toggle_display("diesel_price_html", card_can(frm, 1, "read"));
	if (!card_can(frm, 1, "read")) return;
	const rows = card_price_rows(frm);
	if (!rows.length) {
		field.$wrapper.html(
			`<p class="text-muted">${__("Add the company in the Accounting tab first.")}</p>`,
		);
		return;
	}
	const current = rows.find((r) => r.company === frm._card_price_company) || rows[0];
	frm._card_price_company = current.company;
	const render_id = (frm._card_price_render = (frm._card_price_render || 0) + 1);
	frappe.db.get_value("Company", current.company, "default_currency").then((r) => {
		if (render_id !== frm._card_price_render) return; // a newer render owns the box
		const currency = (r && r.message && r.message.default_currency) || "";
		const price = flt(current.diesel_unit_price);
		const label = currency
			? __("Diesel price per litre ({0})", [__(currency, null, "Card currency")])
			: __("Diesel price per litre");
		const value =
			price > 0
				? `<span style="font-size: var(--text-2xl); font-weight: 600;">${format_currency(
						price,
						currency,
				  )}</span>`
				: `<span class="text-danger">${__("Not set")}</span>`;
		const picker =
			rows.length > 1
				? `<select class="form-control input-sm card-price-company" style="max-width: 320px;">${rows
						.map(
							(row) =>
								`<option value="${frappe.utils.escape_html(row.company)}" ${
									row.company === current.company ? "selected" : ""
								}>${frappe.utils.escape_html(row.company)}</option>`,
						)
						.join("")}</select>`
				: "";
		const edit = card_can_write(frm, 1)
			? `<button class="btn btn-default btn-sm card-price-edit">${__(
					"Change price",
			  )}</button>`
			: "";
		field.$wrapper.html(`
			<div class="frappe-control">
				<label class="control-label">${label}</label>
				${picker}
				<div class="d-flex align-items-center" style="gap: var(--margin-md); margin-top: var(--margin-xs);">
					${value} ${edit}
				</div>
			</div>`);
		field.$wrapper.find(".card-price-company").on("change", (e) => {
			frm._card_price_company = $(e.target).val();
			card_render_diesel_price(frm);
		});
		field.$wrapper
			.find(".card-price-edit")
			.on("click", () => card_edit_diesel_price(frm, current));
	});
}

function card_edit_diesel_price(frm, row) {
	// the price is saved on its own: never together with other unsaved edits on this form
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save or discard your other changes in Card Settings first."));
		return;
	}
	frappe.prompt(
		{
			fieldname: "price",
			fieldtype: "Currency",
			label: __("Diesel price per litre"),
			default: flt(row.diesel_unit_price) || null,
			reqd: 1,
		},
		(values) => {
			if (flt(values.price) <= 0) {
				frappe.throw(__("The diesel price must be greater than zero."));
			}
			frappe.model.set_value(row.doctype, row.name, "diesel_unit_price", flt(values.price));
			frm.save();
		},
		frappe.utils.escape_html(row.company),
	);
}

frappe.ui.form.on("Card Settings", {
	refresh(frm) {
		// the permission roles are changed only by users who may write them (the server enforces it)
		frm.toggle_display(CARD_ADVANCED_ROLES, card_can_write(frm, 2));
		card_render_diesel_price(frm);
	},
});

frappe.ui.form.on("Card Company Settings", {
	company(frm) {
		card_render_diesel_price(frm);
	},
	diesel_unit_price(frm) {
		card_render_diesel_price(frm);
	},
	company_settings_remove(frm) {
		card_render_diesel_price(frm);
	},
});
