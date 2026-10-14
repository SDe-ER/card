// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// CARD brand 5-level heatmap palette (zero level first, like frappe-charts expects).
const CARD_HEATMAP_COLORS = ["#ebedf0", "#b9e9dd", "#74d2bb", "#27b495", "#0b7f63"];

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

// Build a read-only anchor to an EXISTING record (no "create new" affordance).
function card_doc_link(doctype, name) {
	return (
		'<a href="/app/' +
		frappe.router.slug(doctype) +
		"/" +
		encodeURIComponent(name) +
		'">' +
		frappe.utils.escape_html(name) +
		"</a>"
	);
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
				frm.dashboard.add_section(parts.join(""), __("Related records"));
			}
		});
}

frappe.ui.form.on("Card Equipment", {
	setup(frm) {
		card_patch_heatmap(frm);
	},
	refresh(frm) {
		card_patch_heatmap(frm);
		card_render_equipment_links(frm);
	},
});
