// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// Owner 2026-10-20: the diesel price per litre shows on top of Diesel Settings as one clear value.
// FR-125: it is the price of the company's Diesel price schedule row in force today, or, for a company
// without a schedule, Card Company Settings.diesel_unit_price. With a schedule, diesel_unit_price is
// read-only and a price change is a new dated row. Editing either needs write on permlevel 1; the
// server enforces both on save.
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

// FR-133: the server already removes the rows of companies the user may not see; this filter
// stays for the form state between a local edit and the next load
function card_price_rows(frm) {
	const rows = (frm.doc.company_settings || []).filter((r) => r.company);
	const allowed = ((frappe.defaults.get_user_permissions() || {}).Company || []).map(
		(p) => p.doc,
	);
	return allowed.length ? rows.filter((r) => allowed.includes(r.company)) : rows;
}

// FR-125: the company's Diesel price schedule rows, latest first
function card_schedule_rows(frm, company) {
	return (frm.doc.diesel_price_schedule || [])
		.filter((r) => r.company === company && r.valid_from)
		.sort((a, b) => (a.valid_from < b.valid_from ? 1 : -1));
}

// the price a fill dated today takes (the server rule of project_diesel_fill.diesel_price)
function card_price_today(frm, row) {
	const today = frappe.datetime.get_today();
	const current = card_schedule_rows(frm, row.company).find((r) => r.valid_from <= today);
	return current
		? { price: flt(current.unit_price), valid_from: current.valid_from }
		: { price: flt(row.diesel_unit_price), valid_from: null };
}

// FR-125 (review M1): a company with schedule rows changes its price only by a schedule row
function card_lock_unit_prices(frm) {
	const grid = frm.get_field("company_settings") && frm.get_field("company_settings").grid;
	if (!grid) return;
	for (const row of frm.doc.company_settings || []) {
		const grid_row = (grid.grid_rows_by_docname || {})[row.name];
		if (grid_row) {
			grid_row.toggle_editable(
				"diesel_unit_price",
				!card_schedule_rows(frm, row.company).length,
			);
		}
	}
}

function card_render_diesel_price(frm) {
	card_lock_unit_prices(frm);
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
		const today = card_price_today(frm, current);
		const price = today.price;
		const since = today.valid_from
			? `<span class="text-muted">${__("Valid from {0} (Diesel price schedule)", [
					frappe.datetime.str_to_user(today.valid_from),
			  ])}</span>`
			: "";
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
				${since}
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
	if (card_schedule_rows(frm, row.company).length) {
		card_add_schedule_price(frm, row);
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

// FR-125: a company with a Diesel price schedule changes its price by a new dated row; the rows
// before it, and every submitted fill, keep their price (the server checks the row on save)
function card_add_schedule_price(frm, row) {
	frappe.prompt(
		[
			{
				fieldname: "valid_from",
				fieldtype: "Date",
				label: __("Diesel price valid from"),
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
			{
				fieldname: "price",
				fieldtype: "Currency",
				label: __("Diesel price per litre"),
				default: card_price_today(frm, row).price || null,
				reqd: 1,
			},
		],
		(values) => {
			if (flt(values.price) <= 0) {
				frappe.throw(__("The diesel price must be greater than zero."));
			}
			frm.add_child("diesel_price_schedule", {
				company: row.company,
				valid_from: values.valid_from,
				unit_price: flt(values.price),
			});
			frm.refresh_field("diesel_price_schedule");
			// a refused row does not stay on the form
			frm.save().catch(() => frm.reload_doc());
		},
		frappe.utils.escape_html(row.company),
	);
}

frappe.ui.form.on("Card Settings", {
	refresh(frm) {
		// the permission roles are changed only by users who may write them (the server enforces it)
		frm.toggle_display(CARD_ADVANCED_ROLES, card_can_write(frm, 2));
		// FR-133: the server sends a company-restricted user his companies' rows only, and keeps
		// the other companies' rows when he saves
		if ((frm.doc.__onload || {}).card_hidden_company_rows) {
			frm.dashboard.add_comment(
				__(
					"Card Settings rows of companies you are not permitted to see are hidden and stay unchanged when you save.",
				),
				"blue",
				true,
			);
		}
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
	form_render(frm) {
		card_lock_unit_prices(frm);
	},
});

frappe.ui.form.on("Card Diesel Price", {
	company(frm) {
		card_render_diesel_price(frm);
	},
	valid_from(frm) {
		card_render_diesel_price(frm);
	},
	unit_price(frm) {
		card_render_diesel_price(frm);
	},
	diesel_price_schedule_remove(frm) {
		card_render_diesel_price(frm);
	},
});
