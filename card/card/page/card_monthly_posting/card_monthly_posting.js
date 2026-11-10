// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// CARD Monthly Posting (FR-119, #49 #126): pick a company and a month, see each party's
// posting status, preview the lines the next draft would carry, then create or rebuild it.
// The server decides everything: the reads are GET methods with no side effects
// (card.gl.posting.posting_month_parties / preview_month); the buttons call the existing
// card.gl.posting.post_month / rebuild_month, which check role, company and party again.

frappe.pages["card-monthly-posting"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("CARD Monthly Posting"),
		single_column: true,
	});
	new CardMonthlyPosting(page);
};

const CMP_STATUS = {
	"Not posted": ["orange", __("Not posted")],
	Draft: ["blue", __("Draft posting")],
	Posted: ["green", __("Posted")],
};
// GL Posting Log states shown on a posting link
const CMP_LOG_STATUS = { Draft: __("Draft posting"), Submitted: __("Posted") };
const CMP_PARTY_TYPE = { Supplier: __("Supplier"), Customer: __("Customer") };

function cmp_get(method, args = {}) {
	return frappe.call({ method, args, type: "GET" }).then((r) => r.message);
}

class CardMonthlyPosting {
	constructor(page) {
		this.page = page;
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		this.$body = $(`<div class="cmp">
			<div class="cmp-parties"></div>
			<div class="cmp-preview"></div>
		</div>`).appendTo(page.main);
		this.company = page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Select",
			options: [],
			change: () => this.load(),
		});
		this.month = page.add_field({
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: Array.from({ length: 12 }, (_v, i) => String(i + 1)),
			default: String(today.getMonth() + 1),
			change: () => this.load(),
		});
		this.year = page.add_field({
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: today.getFullYear(),
			change: () => this.load(),
		});
		page.set_secondary_action(__("Refresh"), () => this.load(), "refresh");
		// the companies the user may see (company scope is checked again on every call)
		cmp_get("card.api.card_company_options").then((companies) => {
			companies = companies || [];
			this.company.df.options = companies;
			this.company.refresh();
			const preferred = frappe.defaults.get_user_default("Company");
			this.company.set_value(companies.includes(preferred) ? preferred : companies[0] || "");
		});
	}

	args() {
		return {
			company: this.company.get_value(),
			month: this.month.get_value(),
			year: this.year.get_value(),
		};
	}

	load() {
		const args = this.args();
		this.$body.find(".cmp-preview").empty();
		const $parties = this.$body.find(".cmp-parties").empty();
		if (!args.company || !args.month || !args.year) return;
		const request = (this.request = (this.request || 0) + 1);
		return cmp_get("card.gl.posting.posting_month_parties", args).then((rows) => {
			if (request !== this.request) return;
			if (!rows || !rows.length) {
				$parties.append(
					`<div class="cmp-empty text-muted">${__(
						"No CARD documents or postings for this company and month.",
					)}</div>`,
				);
				return;
			}
			$parties.append(this.parties_table(rows));
		});
	}

	parties_table(rows) {
		const e = frappe.utils.escape_html;
		const $table = $(`<table class="table table-bordered cmp-table">
			<thead><tr>
				<th>${__("Party Type")}</th>
				<th>${__("Party")}</th>
				<th>${__("Status")}</th>
				<th class="text-right">${__("Documents not yet in a posting")}</th>
				<th>${__("CARD postings")}</th>
				<th></th>
			</tr></thead><tbody></tbody></table>`);
		const $tbody = $table.find("tbody");
		for (const row of rows) {
			const [color, label] = CMP_STATUS[row.status] || ["gray", e(row.status)];
			const postings = row.postings
				.map(
					(p) =>
						`<a href="/app/${frappe.router.slug(
							p.posting_doctype,
						)}/${encodeURIComponent(p.posting_doc)}">${e(
							p.posting_doc,
						)}</a> <span class="text-muted">(${
							CMP_LOG_STATUS[p.status] || e(p.status)
						}${
							p.origin === "Linked" ? " · " + __("linked supplier invoice") : ""
						})</span>`,
				)
				.join("<br>");
			const $tr = $(`<tr>
				<td>${CMP_PARTY_TYPE[row.party_type]}</td>
				<td>${e(row.party_name || row.party)}${
					row.party_name && row.party_name !== row.party
						? ` <span class="text-muted">${e(row.party)}</span>`
						: ""
				}</td>
				<td><span class="indicator-pill ${color}">${label}</span></td>
				<td class="text-right">${row.pending_sources}</td>
				<td>${postings}</td>
				<td class="text-right"></td>
			</tr>`);
			if (row.pending_sources || row.status === "Draft") {
				$(`<button class="btn btn-default btn-xs">${__("Preview lines")}</button>`)
					.on("click", () => this.preview(row))
					.appendTo($tr.find("td:last"));
			}
			$tbody.append($tr);
		}
		return $table;
	}

	preview(row) {
		const args = Object.assign(this.args(), { party_type: row.party_type, party: row.party });
		const $preview = this.$body.find(".cmp-preview").empty();
		$preview.append(`<div class="text-muted">${__("Loading...")}</div>`);
		return cmp_get("card.gl.posting.preview_month", args).then((p) => {
			$preview.empty().append(this.preview_view(p, args));
		});
	}

	money(value, currency) {
		return format_currency(value, currency);
	}

	preview_view(p, args) {
		const e = frappe.utils.escape_html;
		const $view = $(`<div class="cmp-card">
			<h4>${e(p.party_name || p.party)} — ${e(p.month)}/${e(String(p.year))}</h4>
			<div class="cmp-meta text-muted"></div>
			<div class="cmp-messages"></div>
			<div class="cmp-lines"></div>
			<div class="cmp-totals"></div>
			<div class="cmp-sources"></div>
			<div class="cmp-review"></div>
			<div class="cmp-actions"></div>
		</div>`);
		const meta = [__(p.posting_doctype)];
		if (p.mode === "rebuild") {
			meta.push(__("Rebuild replaces draft {0}", [p.replaces.map(e).join(", ")]));
		}
		if (p.posting_date)
			meta.push(__("Posting date {0}", [frappe.datetime.str_to_user(p.posting_date)]));
		$view.find(".cmp-meta").text(meta.join(" · "));
		const $messages = $view.find(".cmp-messages");
		if (p.blocked) {
			$messages.append(
				`<div class="alert alert-danger">${__("This posting cannot be built yet:")} ${e(
					p.blocked,
				)}</div>`,
			);
			return $view;
		}
		for (const w of p.warnings || [])
			$messages.append(`<div class="alert alert-warning">${e(w)}</div>`);
		if (p.diesel_note)
			$messages.append(`<div class="alert alert-info">${e(p.diesel_note)}</div>`);

		const $lines = $(`<table class="table table-bordered cmp-table">
			<thead><tr>
				<th>${__("Description")}</th>
				<th>${__("Item")}</th>
				<th>${__("Account")}</th>
				<th>${__("Project")}</th>
				<th>${__("Cost Center")}</th>
				<th>${__("Equipment")}</th>
				<th>${__("VAT on the line")}</th>
				<th class="text-right">${__("Amount")}</th>
			</tr></thead><tbody></tbody></table>`);
		for (const item of p.items) {
			const vat = !p.tax_template
				? __("No VAT")
				: item.taxable
				  ? __("Taxable")
				  : __("Zero-rated");
			$lines.find("tbody").append(`<tr>
				<td>${e(item.description || "")}</td>
				<td>${e(item.item_code || "")}</td>
				<td>${e(item.account || "")}</td>
				<td>${e(item.project || "")}</td>
				<td>${e(item.cost_center || "")}</td>
				<td>${e(item.card_equipment || "")}</td>
				<td>${vat}${
					item.item_tax_template
						? ` <span class="text-muted">${e(item.item_tax_template)}</span>`
						: ""
				}</td>
				<td class="text-right">${this.money(item.rate, p.currency)}</td>
			</tr>`);
		}
		$view.find(".cmp-lines").append($lines);

		const totals = [[__("Lines total"), p.net_total + p.discount]];
		if (p.discount)
			totals.push([__("Discount on Net Total (customer deductions)"), -p.discount]);
		totals.push([__("Net total"), p.net_total]);
		if (p.tax_template) {
			totals.push([__("Taxable net"), p.taxable_net]);
			if (p.zero_rated_net) totals.push([__("Zero-rated net"), p.zero_rated_net]);
			totals.push([
				__("VAT {0}% (estimate; ERPNext computes the invoice taxes)", [p.vat_rate]),
				p.vat_estimate,
			]);
		}
		const $totals = $(
			`<table class="table table-condensed cmp-totals-table"><tbody></tbody></table>`,
		);
		for (const [label, value] of totals) {
			$totals
				.find("tbody")
				.append(
					`<tr><td>${label}</td><td class="text-right">${this.money(
						value,
						p.currency,
					)}</td></tr>`,
				);
		}
		$view.find(".cmp-totals").append($totals);
		$view
			.find(".cmp-totals")
			.append(
				`<div class="text-muted">${
					p.tax_template
						? __("Tax template {0}", [e(p.tax_template)])
						: __("No VAT: the supplier has no tax ID.")
				}</div>`,
			);

		const sources = p.sources
			.map(
				(s) =>
					`<a href="/app/${frappe.router.slug(s.doctype)}/${encodeURIComponent(
						s.name,
					)}">${e(s.name)}</a> <span class="text-muted">${__(s.doctype)} · ${this.money(
						s.amount,
						p.currency,
					)}</span>`,
			)
			.join("<br>");
		$view
			.find(".cmp-sources")
			.append(`<h5>${__("Source documents")}</h5><div>${sources}</div>`);

		const reviewed = this.review_section(p, $view.find(".cmp-review"));
		this.action_button(p, args, reviewed).appendTo($view.find(".cmp-actions"));
		return $view;
	}

	review_section(p, $box) {
		// P0: hand-booked supplier invoices around the month must be linked or reviewed first;
		// only an accountant may declare one unrelated (checked again on the server)
		const e = frappe.utils.escape_html;
		const checked = new Set();
		if (!p.review_invoices.length && !p.hidden_review_invoices) return checked;
		$box.append(`<h5>${__("Supplier invoices to review")}</h5>
			<div class="text-muted">${__(
				"These supplier invoices around this month may cover the same operations. Link each one to the CARD documents it pays for, or tick it when an accountant confirms it is unrelated.",
			)}</div>`);
		for (const inv of p.review_invoices) {
			const $row = $(`<div class="checkbox"><label>
				<input type="checkbox" ${p.can_review ? "" : "disabled"}>
				<a href="/app/purchase-invoice/${encodeURIComponent(inv.name)}">${e(inv.name)}</a>
				<span class="text-muted">${e(inv.bill_no || __("no bill no."))}${
					inv.docstatus === 0 ? " · " + __("draft invoice") : ""
				} · ${this.money(inv.grand_total, p.currency)}</span>
			</label></div>`);
			$row.find("input").on("change", (ev) => {
				if (ev.target.checked) checked.add(inv.name);
				else checked.delete(inv.name);
			});
			$box.append($row);
		}
		if (p.hidden_review_invoices) {
			$box.append(
				`<div class="alert alert-warning">${__(
					"{0} more supplier invoice(s) you cannot open must be reviewed by an accountant.",
					[p.hidden_review_invoices],
				)}</div>`,
			);
		}
		if (!p.can_review) {
			$box.append(
				`<div class="text-muted">${__(
					"Only an accountant may declare supplier invoices unrelated.",
				)}</div>`,
			);
		}
		return checked;
	}

	action_button(p, args, reviewed) {
		const rebuild = p.mode === "rebuild";
		const label = rebuild ? __("Rebuild draft posting") : __("Create draft posting");
		return $(`<button class="btn btn-primary btn-sm">${label}</button>`).on("click", () => {
			const message = rebuild
				? __("Delete draft {0} and build it again with the lines shown?", [
						p.replaces.join(", "),
				  ])
				: __("Create a draft {0} with the lines shown?", [__(p.posting_doctype)]);
			frappe.confirm(message, () => {
				frappe
					.call({
						method: rebuild
							? "card.gl.posting.rebuild_month"
							: "card.gl.posting.post_month",
						args: Object.assign({}, args, { reviewed_invoices: Array.from(reviewed) }),
						freeze: true,
					})
					.then((r) => {
						if (!r.message) return;
						frappe.show_alert({
							message: __("Draft posting {0} created.", [r.message]),
							indicator: "green",
						});
						this.load();
						frappe.set_route("Form", p.posting_doctype, r.message);
					});
			});
		});
	}
}
