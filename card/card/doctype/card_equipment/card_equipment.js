// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// CARD brand 5-level heatmap palette (zero level first, like frappe-charts expects).
const CARD_HEATMAP_COLORS = ["#ebedf0", "#b9e9dd", "#74d2bb", "#27b495", "#0b7f63"];
// Distinct night-shift palette (indigo) so ليلي is told apart from نهاري at a glance.
const CARD_NIGHT_COLORS = ["#ebedf0", "#c7d2fe", "#a5b4fc", "#6366f1", "#3730a3"];

// The form-dashboard heatmap hard-codes count_label "interactions" and the default
// palette (frappe/public/js/frappe/form/dashboard.js render_heatmap). Owner decision
// 2026-10-13 (2a): rebuild the chart with the Arabic hour label + brand colors.
// If a future frappe version changes these internals, the guard below simply leaves
// the stock heatmap in place.
function card_patch_heatmap(frm) {
	if (!frm.dashboard || frm.dashboard._card_heatmap_patched) return;
	if (typeof frm.dashboard.render_heatmap !== "function") return;
	frm.dashboard._card_heatmap_patched = true;
	const original = frm.dashboard.render_heatmap.bind(frm.dashboard);
	frm.dashboard.render_heatmap = function () {
		original();
		if (!this.heatmap) return;
		this.heatmap = new frappe.Chart("#heatmap-" + frappe.model.scrub(frm.doctype), {
			type: "heatmap",
			start: new Date(moment().subtract(1, "year").toDate()),
			// frappe-charts Heatmap reads options.countLabel (camelCase); the stock
			// dashboard passes count_label, which the chart ignores — hence the native
			// heatmap shows no label. We set countLabel so the tooltip reads "N ساعة".
			countLabel: __("hour"),
			discreteDomains: 1,
			radius: 3,
			colors: CARD_HEATMAP_COLORS,
			data: {},
		});
		this.heatmap_area.body.find("svg").css({ margin: "auto" });
	};
}

// Render one labelled heatmap into `container` from a {unixTs: hours} map.
function card_build_heatmap(container, title, dataPoints, colors) {
	$('<div class="text-muted" style="margin:10px 0 2px;font-weight:600"></div>')
		.text(title)
		.appendTo(container);
	const el = $("<div></div>").appendTo(container)[0];
	new frappe.Chart(el, {
		type: "heatmap",
		data: {
			dataPoints: dataPoints || {},
			start: new Date(moment().subtract(1, "year").toDate()),
			end: new Date(),
		},
		countLabel: __("hour"),
		discreteDomains: 1,
		radius: 3,
		colors: colors,
	});
	$(el).find("svg").css({ margin: "auto" });
}

// Two-shift equipment: split the Activity heatmap into نهاري + ليلي, each with its
// own palette, so night is told apart from day (owner request 2026-10-14). Single-
// shift equipment keep the one brand heatmap from card_patch_heatmap.
function card_render_shift_heatmaps(frm) {
	if (frm.is_new() || !frm.dashboard || !frm.dashboard.heatmap_area) return;
	frappe
		.call({
			method: "card.card.doctype.card_equipment.card_equipment.get_shift_heatmap",
			args: { name: frm.doc.name },
		})
		.then((r) => {
			const d = (r && r.message) || {};
			const body = frm.dashboard.heatmap_area.body;
			body.find(".card-shift-heatmaps").remove();
			if (!d.has_night) return; // single shift → keep the default single heatmap
			// Take over: hide the native single heatmap and stop its async data overwrite.
			body.find("#heatmap-" + frappe.model.scrub(frm.doctype)).hide();
			frm.dashboard.heatmap = { update: function () {} };
			const wrap = $('<div class="card-shift-heatmaps"></div>').appendTo(body);
			card_build_heatmap(wrap, __("Day-shift activity"), d.day, CARD_HEATMAP_COLORS);
			card_build_heatmap(wrap, __("Night-shift activity"), d.night, CARD_NIGHT_COLORS);
		});
}

// Build a read-only anchor to an EXISTING record (no "create new" affordance).
// get_form_link gives the site-correct URL (fallback for middle-click / new tab);
// the actual click is handled by card_bind_direct_links → frappe.set_route so it
// routes in-app (SPA) instead of a full page reload, and resolves non-ASCII
// docnames + permissions the native way.
function card_doc_link(doctype, name) {
	return (
		'<a href="' +
		frappe.utils.get_form_link(doctype, name) +
		'" class="card-direct-link" data-dt="' +
		frappe.utils.escape_html(doctype) +
		'" data-dn="' +
		frappe.utils.escape_html(name) +
		'">' +
		frappe.utils.escape_html(name) +
		"</a>"
	);
}

// Delegate clicks on the direct links to the in-app router (no full reload).
function card_bind_direct_links(body) {
	$(body)
		.off("click.carddirect")
		.on("click.carddirect", "a.card-direct-link", function (e) {
			e.preventDefault();
			frappe.set_route("Form", $(this).attr("data-dt"), $(this).attr("data-dn"));
		});
}

// Owner decision 2026-10-14: surface, inside the Connections («الارتباطات») tab, a
// DIRECT read-only link to the EXISTING lessor (supplier), the current project, and
// the projects this equipment has actually worked on (distinct projects taken from
// its monthly operation cards). This is a custom dashboard section on purpose:
// Frappe's native connection cards are reverse-only and always render a "+ New"
// create button, which the owner explicitly rejected. No record is ever created here.
function card_render_equipment_links(frm) {
	if (frm.is_new()) return;
	frappe.db
		.get_list("Card Monthly Card", {
			filters: { equipment: frm.doc.name, project: ["is", "set"] },
			fields: ["project"],
			group_by: "project",
			order_by: "project asc",
			limit: 0,
		})
		.then((recs) => {
			const parts = [];
			if (frm.doc.ownership !== "ملك" && frm.doc.supplier) {
				parts.push(
					'<div class="mb-2"><span class="text-muted">' +
						__("Lessor") +
						":</span> " +
						card_doc_link("Supplier", frm.doc.supplier) +
						"</div>",
				);
			}
			if (frm.doc.current_project) {
				parts.push(
					'<div class="mb-2"><span class="text-muted">' +
						__("Current project") +
						":</span> " +
						card_doc_link("Project", frm.doc.current_project) +
						"</div>",
				);
			}
			const projects = (recs || []).map((r) => r.project).filter(Boolean);
			if (projects.length) {
				parts.push(
					'<div class="mb-2"><span class="text-muted">' +
						__("Projects worked on") +
						":</span> " +
						projects.map((p) => card_doc_link("Project", p)).join("، ") +
						"</div>",
				);
			}
			if (parts.length) {
				card_bind_direct_links(
					frm.dashboard.add_section(parts.join(""), __("Related records")),
				);
			}
		});
}

// Owned equipment <-> official ERPNext Asset (rented equipment has no asset).
// Offer only submitted, live Assets of the company that no other equipment links yet.
function card_set_asset_query(frm) {
	frm.set_query("الأصل_في_erpnext", () => ({
		query: "card.api.available_assets_query",
		filters: { company: frm.doc.company || "" },
	}));
}

// FR-077: offer only active models of the chosen make and equipment type.
function card_set_model_query(frm) {
	frm.set_query("equipment_make", () => ({ filters: { disabled: 0 } }));
	frm.set_query("equipment_model", () => {
		const filters = { disabled: 0 };
		if (frm.doc.equipment_make) filters.equipment_make = frm.doc.equipment_make;
		if (frm.doc.equipment_type) filters.equipment_type = frm.doc.equipment_type;
		return { filters };
	});
}

// New-form shortcut: pick an Asset, get a prefilled (unsaved) equipment form.
function card_add_create_from_asset(frm) {
	if (!frm.is_new() || frm.doc["الأصل_في_erpnext"]) return;
	frm.add_custom_button(__("Create from Asset"), () => {
		frappe.prompt(
			[
				{
					fieldname: "asset",
					fieldtype: "Link",
					label: __("Asset"),
					options: "Asset",
					reqd: 1,
					get_query: () => ({
						query: "card.api.available_assets_query",
						filters: { company: frm.doc.company || "" },
					}),
				},
			],
			(values) => {
				frappe
					.call({
						method: "card.api.create_equipment_from_asset",
						args: { asset: values.asset },
					})
					.then((r) => {
						if (!r || !r.message) return;
						const d = r.message;
						const values = {};
						CARD_ASSET_NEW_FIELDS.forEach((f) => d[f] && (values[f] = d[f]));
						frappe.new_doc("Card Equipment", values);
					});
			},
			__("Create from Asset"),
			__("Create"),
		);
	});
}

// F.7: suggest the direction as soon as ownership is known, so the direction-driven
// sections appear immediately (server re-derives anyway). Owned machines are run and
// fuelled by the company.
function card_apply_ownership_defaults(frm) {
	if (!frm.doc.ownership) return;
	const owned = frm.doc.ownership === "ملك";
	// same rule as card.constants.allowed_directions
	const allowed = owned
		? ["مؤجَّرة لعميل", "تشغيل داخلي"]
		: ["مستأجَرة من مورد", "إيجار من الباطن"];
	if (!allowed.includes(frm.doc.rental_direction)) {
		frm.set_value("rental_direction", owned ? "تشغيل داخلي" : "مستأجَرة من مورد");
	}
	// remember what was filled here, so a later switch away from ملك takes it back
	frm._card_auto = frm._card_auto || {};
	["operator_on", "الوقود_على"].forEach((field) => {
		if (owned && !frm.doc[field]) {
			frm.set_value(field, "الشركة");
			frm._card_auto[field] = true;
		} else if (!owned && frm._card_auto[field]) {
			frm.set_value(field, "");
			delete frm._card_auto[field];
		}
	});
	// rented machines are not company Assets
	if (!["ملك", "طرف ثالث"].includes(frm.doc.ownership) && frm.doc["الأصل_في_erpnext"]) {
		frm.set_value("الأصل_في_erpnext", "");
	}
}

const CARD_ASSET_OWNED_FIELDS = [
	"equipment_name",
	"brand",
	"equipment_type",
	"equipment_type_from_asset",
];

const CARD_ASSET_NEW_FIELDS = [
	...CARD_ASSET_OWNED_FIELDS,
	"company",
	"ownership",
	"الأصل_في_erpnext",
	"operator_on",
	"الوقود_على",
	"image",
	"cost_center",
	"operator",
	"insurance_company",
	"insurance_policy_no",
	"insurance_expiry",
];

// The machine is already an ERPNext Asset: its name, brand and type come from the Asset
// (read-only); image, cost center, custodian as operator and insurance fill empty fields.
function card_fill_from_asset(frm) {
	const asset = frm.doc["الأصل_في_erpnext"];
	if (!asset) {
		if (frm.doc.equipment_type_from_asset) frm.set_value("equipment_type_from_asset", 0);
		return;
	}
	frappe
		.call({
			method: "card.api.get_asset_prefill",
			args: { asset },
			type: "GET",
		})
		.then((r) => {
			const d = (r && r.message) || {};
			Object.keys(d).forEach((field) => {
				if (field === "operator" && frm.doc.ownership !== "ملك") return;
				// the Asset owns these (read-only here); the rest only fills empty fields
				if (CARD_ASSET_OWNED_FIELDS.includes(field) || !frm.doc[field]) {
					frm.set_value(field, d[field]);
				}
			});
		});
}

// Documents matter on every machine: say which ones expired or expire within 30 days.
const CARD_DOCUMENT_EXPIRY = [
	"registration_expiry",
	"inspection_expiry",
	"insurance_expiry",
	"tuv_expiry",
];

function card_show_document_alerts(frm) {
	if (frm.is_new()) return;
	const today = frappe.datetime.get_today();
	const expired = [];
	const soon = [];
	CARD_DOCUMENT_EXPIRY.forEach((field) => {
		const date = frm.doc[field];
		if (!date) return;
		const label = __(frappe.meta.get_label(frm.doctype, field));
		const days = frappe.datetime.get_day_diff(date, today);
		if (days < 0) expired.push(label);
		else if (days <= 30) soon.push(label);
	});
	if (expired.length || soon.length) frm._card_doc_alert = true;
	if (expired.length) {
		frm.dashboard.set_headline_alert(
			__("Expired documents: {0}", [expired.join("، ")]),
			"red",
		);
	} else if (soon.length) {
		frm.dashboard.set_headline_alert(
			__("Documents expiring within 30 days: {0}", [soon.join("، ")]),
			"orange",
		);
	} else if (frm._card_doc_alert) {
		frm.dashboard.clear_headline();
		frm._card_doc_alert = false;
	}
}

// v3.0.0: dated changes of a unit's pieces. The unit stays one equipment on its card;
// the server keeps the history and refuses changes inside an approved period.
function card_add_unit_actions(frm) {
	// components are permission level 1: only roles writing that level may change them
	if (frm.is_new() || !frm.doc.is_unit || !frm.perm[1] || !frm.perm[1].write) return;
	const current = (frm.doc.components || []).filter((r) => !r.to_date).map((r) => r.component);
	if (!current.length) return;
	const common = [
		{
			fieldname: "component",
			fieldtype: "Select",
			label: __("Component"),
			options: current,
			reqd: 1,
		},
		{ fieldname: "date", fieldtype: "Date", label: __("From"), default: "Today", reqd: 1 },
		{ fieldname: "reason", fieldtype: "Data", label: __("Change reason") },
	];
	const run = (method, title, extra) =>
		frappe.prompt(
			[...common.slice(0, 1), ...extra, ...common.slice(1)],
			(values) =>
				frappe
					.call({ method, args: { unit: frm.doc.name, ...values }, freeze: true })
					.then(() => frm.reload_doc()),
			title,
			__("Save"),
		);
	const unit_filter = { is_unit: 1, company: frm.doc.company, name: ["!=", frm.doc.name] };
	frm.add_custom_button(
		__("Replace component"),
		() =>
			run(
				"card.card.doctype.card_equipment.card_equipment.replace_component",
				__("Replace component"),
				[
					{
						fieldname: "new_component",
						fieldtype: "Link",
						label: __("New component"),
						options: "Card Equipment",
						reqd: 1,
						get_query: () => ({ filters: { is_unit: 0, company: frm.doc.company } }),
					},
				],
			),
		__("Unit"),
	);
	frm.add_custom_button(
		__("Move to another unit"),
		() =>
			run(
				"card.card.doctype.card_equipment.card_equipment.move_component",
				__("Move to another unit"),
				[
					{
						fieldname: "target_unit",
						fieldtype: "Link",
						label: __("Unit"),
						options: "Card Equipment",
						reqd: 1,
						get_query: () => ({ filters: unit_filter }),
					},
				],
			),
		__("Unit"),
	);
}

frappe.ui.form.on("Card Equipment", {
	setup(frm) {
		card_patch_heatmap(frm);
		card_set_asset_query(frm);
		card_set_model_query(frm);
	},
	refresh(frm) {
		card_patch_heatmap(frm);
		card_add_create_from_asset(frm);
		card_add_unit_actions(frm);
		card_render_shift_heatmaps(frm);
		card_render_equipment_links(frm);
		card_show_document_alerts(frm);
	},
	الأصل_في_erpnext(frm) {
		card_fill_from_asset(frm);
	},
	onload(frm) {
		// a new form starts on ملك: apply its defaults without waiting for a change
		if (frm.is_new()) card_apply_ownership_defaults(frm);
		// one company only: fill it, the field stays editable
		if (frm.is_new() && !frm.doc.company) {
			frappe.call({ method: "card.api.get_only_company", type: "GET" }).then((r) => {
				if (r && r.message && !frm.doc.company) frm.set_value("company", r.message);
			});
		}
	},
	ownership(frm) {
		card_apply_ownership_defaults(frm);
	},
});
