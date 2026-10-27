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
			// a saved exception ends only through the button below, with a reason (Owner 2026-10-20)
			const saved_exception = !frm.is_new() && frm.doc.price_exception;
			frm.set_df_property(
				"price_exception",
				"read_only",
				allowed && !saved_exception ? 0 : 1,
			);
			frm.set_df_property("exception_reason", "read_only", allowed ? 0 : 1);
			if (saved_exception && ctx.can_except) {
				frm.add_custom_button(__("Remove price exception"), () =>
					frappe.prompt(
						{
							fieldname: "reason",
							fieldtype: "Small Text",
							label: __("Reason"),
							reqd: 1,
						},
						(values) =>
							frappe
								.call({
									method: `${CARD_FILL}.remove_price_exception`,
									args: { name: frm.doc.name, reason: values.reason },
								})
								.then(() => frm.reload_doc()),
						__("Remove price exception"),
					),
				);
			}
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
				// changing a saved draft's price is an exception-role decision with a reason (Owner 2026-10-20)
				if (!frm.doc.price_exception && !frm.is_new() && ctx.can_except) {
					frm.add_custom_button(__("Use company price"), () =>
						frappe.prompt(
							{
								fieldname: "reason",
								fieldtype: "Small Text",
								label: __("Reason"),
								reqd: 1,
							},
							(values) =>
								frappe
									.call({
										method: `${CARD_FILL}.use_company_price`,
										args: { name: frm.doc.name, reason: values.reason },
									})
									.then(() => frm.reload_doc()),
							__("Use company price"),
						),
					);
				}
			} else if (
				!frm.is_new() &&
				frm.doc.price_source === "Company Price" &&
				flt(frm.doc.unit_price) !== flt(ctx.price)
			) {
				// a saved draft keeps its price; a later company price change is only shown
				frm.set_intro(
					__("This draft keeps its price {0}; the current company price is {1}.", [
						format_currency(frm.doc.unit_price),
						format_currency(ctx.price),
					]),
					"orange",
				);
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

// Phase 1: the meter readings give the litres (the server sets them again on save)
function card_preview_readings(frm) {
	if (!(flt(frm.doc.closing_reading) > 0)) return; // an empty Float is stored as 0
	const litres = flt(frm.doc.closing_reading) - flt(frm.doc.opening_reading);
	if (litres >= 0 && flt(frm.doc.litres) !== litres) frm.set_value("litres", litres);
}

function card_default_supplier(frm) {
	frappe
		.call({
			method: `${CARD_FILL}.fill_link_query`,
			type: "GET",
			args: { doctype: "Supplier", txt: "", searchfield: "name", start: 0, page_len: 1 },
		})
		.then((r) => {
			const rows = (r && r.message) || [];
			if (rows.length && !frm.doc.supplier) frm.set_value("supplier", rows[0][0]);
		});
}

frappe.ui.form.on("Project Diesel Fill", {
	setup(frm) {
		// P0 (Owner 2026-10-20): fill users cannot search these ERPNext masters directly; the server
		// query lists only what the user may pick for the form's company (and checks it again on save)
		for (const fieldname of ["project", "cost_center", "supplier"]) {
			frm.set_query(fieldname, () => ({
				query: `${CARD_FILL}.fill_link_query`,
				filters: { company: frm.doc.company || "" },
			}));
		}
	},
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
			.then((r) => {
				const editable = r && r.message;
				frm.set_df_property("supplier", "read_only", editable ? 0 : 1);
				// P0: a user who may not change the supplier cannot pick it either; the form takes the
				// Settings supplier (the only one the query returns to that user)
				if (!editable && frm.is_new() && !frm.doc.supplier) card_default_supplier(frm);
			});
		card_price_context(frm);
	},
	company(frm) {
		card_price_context(frm);
	},
	litres(frm) {
		card_preview_amount(frm);
	},
	opening_reading(frm) {
		card_preview_readings(frm);
	},
	closing_reading(frm) {
		card_preview_readings(frm);
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
