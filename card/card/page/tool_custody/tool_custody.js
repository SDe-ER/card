// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// Tool Custody (#113 PR-T3): awaiting handovers, held tools and history in one screen.
// The server decides everything (card.tool_custody): this page shows the actions it returns,
// fills in defaults and sends one request per step.

frappe.pages["tool-custody"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Tool Custody"),
		single_column: true,
	});
	new ToolCustodyScreen(page);
};

const TC_TABS = {
	awaiting: __("Awaiting"),
	held: __("Held tools"),
	history: __("History"),
};
const TC_MOVES = {
	Handover: __("Handover"),
	Return: __("Return"),
	Transfer: __("Transfer"),
	Loss: __("Loss"),
	Damage: __("Damage"),
};
const TC_RECEIPT_FORMAT = "Tool Handover Receipt";
// employees and stores come from the screen's own searches (company and User Permission scoped):
// the screen roles need no Employee or Warehouse read
const TC_EMPLOYEE_QUERY = "card.tool_custody.employee_query";
const TC_STORE_QUERY = "card.tool_custody.store_query";

// the screen's reads are GET methods on the server (no side effects); frappe.xcall sends POST
function tc_get(method, args = {}) {
	return frappe.call({ method, args, type: "GET" }).then((r) => r.message);
}

class ToolCustodyScreen {
	constructor(page) {
		this.page = page;
		this.start = 0;
		this.$body = $(`<div class="tc">
			<div class="tc-tabs" role="tablist"></div>
			<div class="tc-rows"></div>
			<div class="tc-more"><button class="btn btn-default btn-sm">${__("Load more")}</button></div>
		</div>`).appendTo(page.main);
		this.$body.find(".tc-more button").on("click", () => this.load(true));
		this.employee = page.add_field({
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			// the filter also finds a worker who left and still holds tools
			get_query: () => ({ query: TC_EMPLOYEE_QUERY, filters: { any_status: 1 } }),
			change: () => this.ctx && this.load(),
		});
		this.item = page.add_field({
			fieldname: "item_code",
			label: __("Tool"),
			fieldtype: "Link",
			options: "Item",
			change: () => this.ctx && this.load(),
		});
		tc_get("card.tool_custody.context").then((ctx) => {
			this.ctx = ctx;
			this.tab = ctx.default_tab;
			if (ctx.can_prepare) {
				page.set_primary_action(
					__("New handover"),
					() => this.new_movement("Handover"),
					"add",
				);
			}
			this.render_tabs();
			this.load();
		});
	}

	render_tabs() {
		const $tabs = this.$body.find(".tc-tabs").empty();
		for (const tab of this.ctx.tabs) {
			$(`<button class="btn btn-sm ${tab === this.tab ? "btn-primary" : "btn-default"}"
				role="tab" aria-selected="${tab === this.tab}">${TC_TABS[tab]}</button>`)
				.on("click", () => {
					this.tab = tab;
					this.render_tabs();
					this.load();
				})
				.appendTo($tabs);
		}
	}

	load(more = false) {
		// only the latest request draws; rows are drawn for the tab they were read for
		const request = (this.request = (this.request || 0) + 1);
		const start = more ? this.start + 25 : 0;
		return tc_get("card.tool_custody.view", {
			tab: this.tab,
			employee: this.employee.get_value() || null,
			item_code: this.item.get_value() || null,
			start,
		}).then((r) => {
			if (request !== this.request) return;
			this.start = start;
			const $rows = this.$body.find(".tc-rows");
			if (!more) $rows.empty();
			if (!r.rows.length && !more) {
				$rows.append(`<div class="tc-empty text-muted">${__("Nothing here.")}</div>`);
			}
			for (const row of r.rows) $rows.append(this.render_row(row, r.tab));
			this.$body.find(".tc-more").toggle(r.more);
		});
	}

	render_row(row, tab) {
		const e = frappe.utils.escape_html;
		const $row = $(`<div class="tc-row"></div>`);
		let pill, who, what, where, when;
		if (tab === "awaiting") {
			const closed =
				row.movement === "Handover" && row.handover_status === "Not handed over";
			pill = closed
				? ["gray", __("Not handed over")]
				: row.waiting_for_stock
				  ? ["orange", __("Waiting for stock")]
				  : ["blue", TC_MOVES[row.movement]];
			who = this.who(row);
			what = `${e(row.item_name || row.item_code)}`;
			where = [row.card_equipment, row.project].filter(Boolean).map(e).join(" · ");
			when = frappe.datetime.comment_when(row.creation);
			if (closed && row.not_handed_reason) where = `${where} — ${e(row.not_handed_reason)}`;
		} else if (tab === "held") {
			pill = ["green", __("Held")];
			who = e(row.employee_name || row.employee);
			what = e(row.item_name || row.item_code);
			where = "";
			when = "";
		} else {
			pill =
				row.docstatus === 2 ? ["red", __("Cancelled")] : ["green", TC_MOVES[row.movement]];
			who = this.who(row);
			what = e(row.item_name || row.item_code);
			const links = [row.stock_entry, row.review].filter(Boolean).map(e).join(" · ");
			where = [row.card_equipment, row.project].filter(Boolean).map(e).join(" · ");
			if (links) where = where ? `${where} — ${links}` : links;
			when = row.handed_on ? frappe.datetime.comment_when(row.handed_on) : e(row.date || "");
		}
		$row.append(`<span class="tc-pill"><span class="indicator-pill ${pill[0]}">${
			pill[1]
		}</span></span>
			<span class="tc-who">${who}</span>
			<span class="tc-what">${what}</span>
			<span class="tc-qty">${frappe.format(row.qty, { fieldtype: "Float" })}</span>
			<span class="tc-where text-muted">${where}</span>
			<span class="tc-when text-muted">${when}</span>
			<span class="tc-actions"></span>`);
		const $actions = $row.find(".tc-actions");
		for (const action of row.actions || []) {
			$actions.append(this.action_button(action, row));
		}
		if (row.name) {
			$(`<a class="btn btn-default btn-xs" title="${__("Open")}">${__("Open")}</a>`)
				.on("click", () => frappe.set_route("Form", "Employee Tool Custody", row.name))
				.appendTo($actions);
		}
		return $row;
	}

	who(row) {
		// a transfer shows who gives the tool and who receives it
		const e = frappe.utils.escape_html;
		const to = row.to_employee ? ` → ${e(row.to_employee_name || row.to_employee)}` : "";
		return e(row.employee_name || row.employee || "") + to;
	}

	action_button(action, row) {
		const labels = {
			confirm: __("Confirm"),
			not_handed: __("Not handed over"),
			replace: __("New handover for the rest"),
			return: __("Return"),
			transfer: __("Transfer"),
		};
		const primary = ["confirm", "return"].includes(action);
		return $(
			`<button class="btn btn-xs ${primary ? "btn-primary" : "btn-default"}">${
				labels[action]
			}</button>`,
		).on("click", () => this[`do_${action}`](row));
	}

	// ---- actions (each one server call; the server checks everything again) ----
	do_confirm(row) {
		// the server says whether the tool needs a Serial No (the user may not read Item)
		this.confirm_dialog(row, !!row.has_serial_no);
	}

	confirm_dialog(row, serial) {
		const needs_receipt = ["Handover", "Transfer"].includes(row.movement);
		const e = frappe.utils.escape_html;
		const d = new frappe.ui.Dialog({
			title: __("Confirm {0}", [TC_MOVES[row.movement]], "Tool Custody"),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "summary",
					options: `<p><b>${this.who(row)}</b> · ${e(
						row.item_name || row.item_code,
					)}</p>`,
				},
				{
					fieldtype: "Float",
					fieldname: "qty",
					label: __("Quantity"),
					default: row.qty,
					reqd: 1,
				},
				...(serial
					? [
							{
								fieldtype: "Data",
								fieldname: "serial_no",
								label: __("Serial No"),
								reqd: 1,
							},
					  ]
					: []),
				{
					fieldtype: "Button",
					fieldname: "print",
					label: __("Print receipt"),
					click: () => this.print_receipt(row.name),
				},
				{
					fieldtype: "Attach",
					fieldname: "receipt",
					label: __("Signed receipt"),
					reqd: needs_receipt ? 1 : 0,
				},
				{
					fieldtype: "HTML",
					fieldname: "note",
					options: `<p class="text-muted small">${__(
						"Attaching the file does not verify the signature.",
					)}</p>`,
				},
			],
			primary_action_label: __("Confirm"),
			primary_action: (v) =>
				frappe
					.xcall("card.tool_custody.confirm", {
						custody: row.name,
						receipt: v.receipt || null,
						qty: v.qty,
						serial_no: v.serial_no || null,
					})
					.then((r) => {
						d.hide();
						frappe.show_alert({
							message: r.stock_entry
								? __("Confirmed. Stock moved: {0}", [r.stock_entry])
								: __("Confirmed."),
							indicator: "green",
						});
						this.load();
					}),
		});
		d.show();
	}

	do_not_handed(row) {
		frappe.prompt(
			{ fieldtype: "Small Text", fieldname: "reason", label: __("Reason"), reqd: 1 },
			(v) =>
				frappe
					.xcall("card.materials.close_tool_handover", {
						custody: row.name,
						reason: v.reason,
					})
					.then(() => this.load()),
			__("Not handed over"),
			__("Save"),
		);
	}

	do_replace(row) {
		frappe.confirm(
			__("Make a new handover for the tools of this line that are not handed over?"),
			() =>
				frappe
					.xcall("card.materials.make_tool_handover", { review_item: row.review_item })
					.then(() => this.load()),
		);
	}

	do_return(row) {
		this.new_movement("Return", row);
	}

	do_transfer(row) {
		this.new_movement("Transfer", row);
	}

	new_movement(movement, row = {}) {
		// a return or transfer stays in the worker's company: offer only its stores and employees
		// (the server checks it)
		this.movement_dialog(movement, row, row.company);
	}

	movement_dialog(movement, row, company) {
		const e = frappe.utils.escape_html;
		const fields = [];
		if (row.employee) {
			// a return or transfer starts from a held tool: say whose and which
			fields.push({
				fieldtype: "HTML",
				fieldname: "summary",
				options: `<p><b>${e(row.employee_name || row.employee)}</b> · ${e(
					row.item_name || row.item_code,
				)} · ${__("Held")}: ${frappe.format(
					row.qty,
					{ fieldtype: "Float" },
					{ inline: true },
				)}</p>`,
			});
		} else {
			fields.push({
				fieldtype: "Link",
				fieldname: "employee",
				label: __("Employee"),
				options: "Employee",
				reqd: 1,
				get_query: () => ({ query: TC_EMPLOYEE_QUERY }),
			});
		}
		if (!row.item_code) {
			fields.push({
				fieldtype: "Link",
				fieldname: "item_code",
				label: __("Tool"),
				options: "Item",
				reqd: 1,
				get_query: () => ({
					filters: { is_stock_item: 1, is_fixed_asset: 0, disabled: 0 },
				}),
			});
		}
		if (movement === "Transfer") {
			fields.push({
				fieldtype: "Link",
				fieldname: "to_employee",
				label: __("To employee"),
				options: "Employee",
				reqd: 1,
				get_query: () => ({
					query: TC_EMPLOYEE_QUERY,
					filters: { exclude: row.employee, ...(company ? { company } : {}) },
				}),
			});
		} else {
			fields.push({
				fieldtype: "Link",
				fieldname: "warehouse",
				label: __("Store"),
				options: "Warehouse",
				default: this.ctx.default_store,
				reqd: 1,
				get_query: () => ({ query: TC_STORE_QUERY, filters: company ? { company } : {} }),
			});
		}
		fields.push({
			fieldtype: "Float",
			fieldname: "qty",
			label: __("Quantity"),
			default: row.qty || 1,
			reqd: 1,
		});
		const d = new frappe.ui.Dialog({
			title: TC_MOVES[movement],
			fields,
			primary_action_label: __("Next"),
			primary_action: (v) =>
				frappe
					.xcall("card.tool_custody.move", {
						movement,
						employee: row.employee || v.employee,
						item_code: row.item_code || v.item_code,
						qty: v.qty,
						to_employee: v.to_employee || null,
						warehouse: v.warehouse || null,
					})
					.then((r) => {
						d.hide();
						this.tab = "awaiting";
						this.render_tabs();
						this.load().then(() => {
							// a user the server lets confirm does it at once (print, sign, attach);
							// others leave it waiting
							if (r.may_confirm) {
								this.do_confirm({
									name: r.name,
									movement,
									employee: row.employee || v.employee,
									employee_name: r.employee_name,
									to_employee: v.to_employee,
									to_employee_name: r.to_employee_name,
									item_code: row.item_code || v.item_code,
									item_name: row.item_name,
									qty: v.qty,
									has_serial_no: r.has_serial_no,
								});
							}
						});
					}),
		});
		d.show();
	}

	print_receipt(name) {
		const url =
			"/printview?doctype=" +
			encodeURIComponent("Employee Tool Custody") +
			"&name=" +
			encodeURIComponent(name) +
			"&format=" +
			encodeURIComponent(TC_RECEIPT_FORMAT) +
			"&trigger_print=1";
		window.open(frappe.urllib.get_full_url(url), "_blank", "noopener");
	}
}
