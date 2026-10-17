// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// The registry row stores no figures (#23): they are fetched per company the
// user may see (card.api.party_figures) and shown on the form.
frappe.ui.form.on("Card Equipment Customer", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe
			.call({
				method: "card.api.party_figures",
				args: { party_type: "Customer", party: frm.doc.name },
			})
			.then((r) => {
				const rows = r.message || [];
				card_show_party_figures(frm, rows, __("Total accrued (cards)"));
				frm.add_custom_button(__("Statement"), () => {
					// default period = last operating month on record, else previous calendar month
					const last = rows
						.map((x) => x.last_month)
						.filter(Boolean)
						.sort()
						.pop();
					let y, m;
					if (last) {
						y = parseInt(last.slice(0, 4));
						m = last.slice(5, 7);
					} else {
						const p = new Date(new Date().getFullYear(), new Date().getMonth() - 1, 1);
						y = p.getFullYear();
						m = String(p.getMonth() + 1).padStart(2, "0");
					}
					const route = {
						customer: frm.doc.name,
						from_month: m,
						from_year: y,
						to_month: m,
						to_year: y,
					};
					if (rows.length === 1) route.company = rows[0].company;
					frappe.set_route("query-report", "Equipment Customer Statement", route);
				}).addClass("btn-primary");
			});
	},
});

function card_show_party_figures(frm, rows, money_label) {
	if (!rows.length) return;
	const esc = frappe.utils.escape_html;
	const head = [
		__("Company"),
		__("Equipment"),
		__("Cards"),
		__("Operating hours"),
		money_label,
		__("Period"),
	]
		.map((h) => `<th>${esc(h)}</th>`)
		.join("");
	const body = rows
		.map(
			(x) =>
				`<tr><td>${esc(x.company)}</td><td>${x.equipment_count}</td><td>${
					x.card_count
				}</td>` +
				`<td>${format_number(x.total_hours, null, 2)}</td><td>${format_currency(
					x.total,
				)}</td>` +
				`<td>${esc(x.first_month || "")} – ${esc(x.last_month || "")}</td></tr>`,
		)
		.join("");
	frm.dashboard.add_section(
		`<table class="table table-bordered table-sm"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`,
		__("Figures per company"),
	);
}
