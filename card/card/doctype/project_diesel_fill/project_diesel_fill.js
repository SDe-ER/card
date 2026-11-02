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
			// the price exception section is for the exception roles, or a fill that already has one
			frm.toggle_display("price_section", !!(allowed || frm.doc.price_exception));
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

// the meter photos are shown as a large card in place of the file link, so the meter can be read on
// the form (Owner 2026-10-27); the card keeps the control's own remove and change actions. The
// standard Attach Image control only shows the file name, with a small preview on hover
function card_photo_previews(frm) {
	for (const fieldname of ["opening_photo", "closing_photo"]) {
		const field = frm.get_field(fieldname);
		if (!field || !field.$wrapper) continue;
		let $preview = field.$wrapper.find(".card-meter-photo");
		if (!$preview.length) {
			$preview = $('<div class="card-meter-photo"></div>').appendTo(field.$wrapper);
		}
		const url = frm.doc[fieldname] || "";
		// only a file of this site (/files or /private/files); anything else keeps the standard link
		const shown = /^\/(private\/)?files\//.test(url);
		// the link of an editable field, and the text of a read-only one
		field.$wrapper.find(".attached-file, .control-value").toggleClass("d-none", shown);
		if (!shown) {
			$preview.empty();
			continue;
		}
		const src = frappe.utils.escape_html(url);
		const label = frappe.utils.escape_html(__(field.df.label));
		const editable = field.disp_status === "Write";
		const button = (action, icon, title) =>
			`<button type="button" class="btn btn-default btn-sm" data-action="${action}"
				title="${title}" aria-label="${title}">${frappe.utils.icon(icon, "sm")}</button>`;
		$preview.html(
			`<div style="position: relative; margin-top: var(--margin-sm);">
				<a href="${src}" target="_blank" rel="noopener noreferrer">
					<img src="${src}" alt="${label}"
						style="display: block; width: 100%; max-height: 480px; object-fit: contain;
							border: 1px solid var(--border-color); border-radius: var(--border-radius-lg);
							background: var(--subtle-fg);">
				</a>
				${
					editable
						? `<div class="flex" style="position: absolute; top: var(--padding-sm);
								inset-inline-end: var(--padding-sm); gap: var(--margin-xs);">
								${button("change", "es-line-camera", __("Change"))}
								${button("remove", "es-line-close", __("Remove"))}
							</div>`
						: ""
				}
			</div>`,
		);
		// the control's own actions: the uploader for images, and remove with its confirmation
		$preview.find("[data-action=change]").on("click", () => field.on_attach_doc_image());
		$preview.find("[data-action=remove]").on("click", () => field.clear_attachment());
	}
}

// Meter extraction (Owner 2026-11-02): the disputed reading and the crop of the counter, shown from what the fill already
// holds: the `Meter reading (opening|closing): ...` lines the server writes into evidence_warnings, and the private crop
// Files it attaches to the fill (listed by the form's own docinfo, so the fill's permissions apply). No field is added.
// Everything is shown as text (never as HTML), and only /private/files/meter-crop-*.jpg of this site is displayed.
const CARD_METER_SIDES = ["opening", "closing"];
const CARD_METER_LINE = /^Meter reading \((opening|closing)\):\s*(.+)$/;
const CARD_METER_CROP = /^meter-crop-(opening|closing)-([0-9a-f]{16})-v[A-Za-z0-9._-]{1,32}\.jpg$/;

// {opening: "0042? (between 42 and 43 L); flags: ...", closing: ...}: the first line of each side, control characters removed
function card_meter_lines(text) {
	const lines = {};
	for (const line of String(text || "").split("\n")) {
		const match = CARD_METER_LINE.exec(line.trim());
		if (match && !lines[match[1]]) {
			lines[match[1]] = match[2].replace(/[\u0000-\u001f\u007f]/g, " ").slice(0, 300);
		}
	}
	return lines;
}

// {opening: {url, name}, closing: {...}}: the first (newest) crop of each side among a fill's attachments
function card_meter_crops(attachments) {
	const crops = {};
	for (const row of attachments || []) {
		const match = CARD_METER_CROP.exec(row.file_name || "");
		const url = row.file_url || "";
		if (!match || crops[match[1]] || !/^\/private\/files\/[A-Za-z0-9._-]+$/.test(url))
			continue;
		crops[match[1]] = { url, name: row.file_name };
	}
	return crops;
}

// The server-built line is English/numeric text ("1501.? (between 1501 and 1501.9 L); flags: glare"). Inside an Arabic (RTL)
// sentence the bidi algorithm would move its brackets, punctuation and the "?" around; an LTR isolate keeps the line exactly
// as written. The worker text is still escaped, so nothing in it can become markup.
function card_ltr_isolate(text) {
	return `<bdi dir="ltr" style="unicode-bidi: isolate;">${frappe.utils.escape_html(text)}</bdi>`;
}

function card_meter_extraction(frm) {
	if (frm.is_new()) return;
	const lines = card_meter_lines(frm.doc.evidence_warnings);
	const crops = card_meter_crops((frm.get_docinfo() || {}).attachments);
	for (const side of CARD_METER_SIDES) {
		// the disputed reading right under the reading it concerns (empty again once the server dropped the line)
		frm.set_df_property(
			`${side}_reading`,
			"description",
			lines[side]
				? __("Disputed by meter extraction: {0}", [card_ltr_isolate(lines[side])])
				: "",
		);
		const field = frm.get_field(`${side}_photo`);
		if (!field || !field.$wrapper) continue;
		let $box = field.$wrapper.find(".card-meter-extraction");
		if (!$box.length) {
			$box = $('<div class="card-meter-extraction"></div>').appendTo(field.$wrapper);
		}
		$box.empty();
		if (!crops[side]) continue;
		const photo = frm.doc[`${side}_photo`] || "";
		const full = /^\/(private\/)?files\//.test(photo) ? photo : crops[side].url;
		const $link = $('<a target="_blank" rel="noopener noreferrer"></a>')
			.attr("href", full)
			.attr("title", __("Open the full photo"));
		$("<img>")
			.attr({ src: crops[side].url, alt: __("Meter extraction crop") })
			.css({
				display: "block",
				"max-width": "100%",
				"max-height": "160px",
				"object-fit": "contain",
				"margin-top": "var(--margin-sm)",
				border: "1px solid var(--border-color)",
				"border-radius": "var(--border-radius-lg)",
				background: "var(--subtle-fg)",
			})
			.appendTo($link);
		$link.appendTo($box);
	}
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
		// one company only: fill it and keep it out of the way, as on Equipment Transport (the
		// server still validates it); with several companies the user picks one
		frappe.call({ method: "card.api.get_only_company", type: "GET" }).then(async (r) => {
			const only = r && r.message;
			if (!only) return;
			if (frm.is_new() && !frm.doc.company) await frm.set_value("company", only);
			if (frm.doc.company === only) frm.toggle_display("company", false);
		});
	},
	refresh(frm) {
		card_photo_previews(frm);
		card_meter_extraction(frm);
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
	opening_photo(frm) {
		card_photo_previews(frm);
	},
	closing_photo(frm) {
		card_photo_previews(frm);
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
