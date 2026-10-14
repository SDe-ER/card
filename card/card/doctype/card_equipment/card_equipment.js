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
			countLabel: __("ساعة"),
			discreteDomains: 1,
			radius: 3,
			colors: CARD_HEATMAP_COLORS,
			data: {},
		});
		this.heatmap_area.body.find("svg").css({ margin: "auto" });
	};
}

frappe.ui.form.on("Card Equipment", {
	setup(frm) {
		card_patch_heatmap(frm);
	},
	refresh(frm) {
		card_patch_heatmap(frm);
	},
});
