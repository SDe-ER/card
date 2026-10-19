// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// F.1/F.3: company auto-fills from the user's default; the diesel supplier is
// read-only under the Fixed policy, and under Variable for users without the
// permitted role (the server enforces both — this only mirrors it in the form).
// Fill users cannot read Card Settings: the server answers yes/no for the supplier.
// FR-002: the price per litre comes from the company price; only the exception role may
// type another one (the server enforces it — this only mirrors it and previews the amount).
const CARD_FILL = "card.card.doctype.project_diesel_fill.project_diesel_fill";

function card_price_context(frm) {
	if (frm.doc.docstatus !== 0) return;
	frappe
		.call({
			method: `${CARD_FILL}.get_diesel_price_context`,
			args: { company: frm.doc.company || null },
			type: "GET",
		})
		.then((r) => {
			const ctx = (r && r.message) || {};
			frm._card_price = ctx;
			const allowed = ctx.can_except || ctx.can_zero;
			frm.set_df_property("price_exception", "read_only", allowed ? 0 : 1);
			frm.set_df_property("exception_reason", "read_only", allowed ? 0 : 1);
			card_price_lock(frm);
			// an amended copy keeps its price until someone decides (the server marks it Needs Review)
			if (frm.is_new() && !frm.doc.price_exception && !frm.doc.amended_from) {
				card_preview_price(frm);
			}
			frm.set_intro();
			// a draft saved before the price lock has no price source yet: show its conflict on open
			const legacy_conflict =
				!frm.is_new() &&
				!frm.doc.price_source &&
				flt(frm.doc.unit_price) !== flt(ctx.price);
			if (frm.doc.price_source === "Needs Review" || legacy_conflict) {
				frm.set_intro(
					__(
						"This draft has price {0}; the company price is {1}. Use the company price, or ask {2} to approve an exception.",
						[
							format_currency(frm.doc.unit_price),
							format_currency(ctx.price),
							ctx.exception_role ? __(ctx.exception_role) : "-",
						],
					),
					"red",
				);
				if (!frm.doc.price_exception && !frm.is_new()) {
					frm.add_custom_button(__("Use company price"), () =>
						frappe
							.call({
								method: `${CARD_FILL}.use_company_price`,
								args: { name: frm.doc.name },
							})
							.then(() => frm.reload_doc()),
					);
				}
			}
		});
}

function card_price_lock(frm) {
	const ctx = frm._card_price || {};
	const open = frm.doc.price_exception && (ctx.can_except || ctx.can_zero);
	frm.set_df_property("unit_price", "read_only", open ? 0 : 1);
}

function card_preview_price(frm) {
	const price = flt((frm._card_price || {}).price);
	if (flt(frm.doc.unit_price) !== price) frm.set_value("unit_price", price);
	card_preview_amount(frm);
}

function card_preview_amount(frm) {
	const amount = flt(flt(frm.doc.litres) * flt(frm.doc.unit_price), 2);
	if (flt(frm.doc.amount) !== amount) frm.set_value("amount", amount);
}

frappe.ui.form.on("Project Diesel Fill", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
		// one company only: fill it, the field stays editable
		if (frm.is_new() && !frm.doc.company) {
			frappe.call({ method: "card.api.get_only_company", type: "GET" }).then((r) => {
				if (r && r.message && !frm.doc.company) frm.set_value("company", r.message);
			});
		}
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frappe
			.call({
				method: `${CARD_FILL}.get_supplier_editable`,
				type: "GET",
			})
			.then((r) => frm.set_df_property("supplier", "read_only", r && r.message ? 0 : 1));
		card_price_context(frm);
	},
	company(frm) {
		card_price_context(frm);
	},
	litres(frm) {
		card_preview_amount(frm);
	},
	unit_price(frm) {
		card_preview_amount(frm);
	},
	price_exception(frm) {
		card_price_lock(frm);
		if (!frm.doc.price_exception && frm.is_new() && !frm.doc.amended_from)
			card_preview_price(frm);
	},
});
