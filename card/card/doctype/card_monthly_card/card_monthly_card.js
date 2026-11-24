const CARD_DAYS = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];

function card_pad(n) {
	return String(n).padStart(2, "0");
}

function card_color_fridays(frm) {
	const paint = () => {
		const grid = frm.fields_dict.days && frm.fields_dict.days.grid;
		if (!grid) return;
		(grid.grid_rows || []).forEach((gr) => {
			const is_friday = gr.doc && gr.doc.day_name === "الجمعة";
			const color = is_friday ? "rgba(255, 165, 0, 0.18)" : "";
			$(gr.wrapper).find(".data-row").css("background-color", color);
			$(gr.wrapper)
				.find(".grid-static-col, .static-area")
				.css("background-color", is_friday ? "transparent" : "");
		});
	};
	setTimeout(paint, 300);
	setTimeout(paint, 900);
}

function card_fill_days(frm) {
	const m = parseInt(frm.doc.month);
	const y = parseInt(frm.doc.year);
	if (!m || !y || y < 2000) return;

	const last = new Date(y, m, 0).getDate();
	frm.set_value("from_date", `${y}-${card_pad(m)}-01`);
	frm.set_value("to_date", `${y}-${card_pad(m)}-${card_pad(last)}`);

	frm.clear_table("days");
	// only the days the equipment was on the card's project (from card_lock_project);
	// no approved transport that month: no day rows at all
	const eligible = frm._card_days || null;
	if (eligible && !eligible.size) {
		frm.refresh_field("days");
		card_calc(frm);
		return;
	}
	for (let d = 1; d <= last; d++) {
		const date = `${y}-${card_pad(m)}-${card_pad(d)}`;
		if (eligible && !eligible.has(date)) continue;
		const dt = new Date(y, m - 1, d);
		const row = frm.add_child("days");
		row.operation_date = date;
		row.day_name = CARD_DAYS[dt.getDay()];
		row.day_status = "عمل";
		row.working_hours = 0;
	}
	frm.refresh_field("days");
	card_calc(frm);
}

// Period the existing rows were built for: taken from from_date (reflects the rows, not the month field)
function card_built_period(frm) {
	const fd = frm.doc.from_date;
	return fd ? { m: String(fd).slice(5, 7), y: parseInt(String(fd).slice(0, 4)) } : null;
}

// Restore month/year without touching rows or hours; the flag blocks re-entry into card_build
function card_revert_period(frm, prev) {
	if (!prev) return;
	frm._card_reverting = true;
	Promise.all([frm.set_value("month", prev.m), frm.set_value("year", prev.y)]).finally(() => {
		frm._card_reverting = false;
	});
}

function card_build(frm) {
	if (frm._card_reverting) return;
	if (!frm.doc.month || !frm.doc.year) return;
	const prev = card_built_period(frm);
	// days never generated yet (e.g. the blank row Frappe adds to a mandatory table): build directly, no prompt
	const has_data = (frm.doc.days || []).some((r) => r.operation_date || flt(r.working_hours));
	if (!prev && !has_data) {
		card_fill_days(frm);
		return;
	}
	if ((frm.doc.days || []).length) {
		if (
			prev &&
			prev.m === card_pad(parseInt(frm.doc.month)) &&
			prev.y === parseInt(frm.doc.year)
		)
			return;
		// first answer wins: a late or duplicate Yes/No callback is ignored
		const target = { m: frm.doc.month, y: frm.doc.year };
		let decided = null;
		frappe.confirm(
			"سيتم إعادة إنشاء أيام الشهر ومسح الساعات المسجلة. متابعة؟",
			() => {
				if (decided) return;
				decided = "yes";
				if (frm.doc.month !== target.m || frm.doc.year !== target.y) return;
				card_fill_days(frm);
			},
			() => {
				if (decided) return;
				decided = "no";
				card_revert_period(frm, prev);
			},
		);
	} else {
		card_fill_days(frm);
	}
}

// Client-side guard: every day row must belong to the selected month and year
function card_check_period(frm) {
	if (!frm.doc.month || !frm.doc.year) return;
	const p = `${parseInt(frm.doc.year)}-${card_pad(parseInt(frm.doc.month))}-`;
	const bad = (frm.doc.days || []).filter((r) => !String(r.operation_date || "").startsWith(p));
	if (bad.length) {
		frappe.throw(
			`تواريخ الأيام لا تطابق الشهر والسنة المختارين (${bad.length} صف). أعد اختيار الشهر لإعادة إنشاء الأيام.`,
		);
	}
}

// The hourly rate is the exact one the server prices with (card_exact_hourly, mirror of
// card.card_value.exact_hourly_rate). Display only: the server recalculates on save.
function card_load_hourly(frm) {
	if (!frm.doc.equipment) {
		frm._card_hourly = 0;
		frm._card_full_day_rate = null;
		frm._card_supplier_side = false;
		return Promise.resolve();
	}
	return frappe.db
		.get_value("Card Equipment", frm.doc.equipment, [
			"approved_hourly_rate",
			"rental_direction",
			"ownership",
			"customer_rate",
			"customer_rate_night",
			"rate_type",
			"rate",
			"day_billing_basis",
			"daily_hours",
		])
		.then((r) => {
			const v = (r && r.message) || {};
			// the exact hourly rate the server prices with (rate / daily hours, e.g. 425 / 8 = 53.125),
			// never the 2-decimal approved_hourly_rate shown on the equipment (card.card_value.exact_hourly_rate)
			return card_exact_hourly(v).then((hourly) => [v, hourly]);
		})
		.then(([v, hourly]) => {
			frm._card_hourly = hourly;
			// FR-138: a per-day rate under "Full day" bills each billed day at the day rate
			// (mirror of card.card_value.bills_full_days; the server recalculates on save)
			frm._card_full_day_rate =
				v.rate_type === "باليوم" && v.day_billing_basis === "Full day"
					? flt(v.rate)
					: null;
			// F.7: only supplier-billing directions accrue a supplier amount
			const dir =
				v.rental_direction || (v.ownership === "ملك" ? "تشغيل داخلي" : "مستأجَرة من مورد");
			frm._card_supplier_side = ["مستأجَرة من مورد", "إيجار من الباطن"].includes(dir);
			card_show_shift_customer_rate(frm, dir, v);
			card_calc(frm);
		});
}

// FR-109: a night-shift card of a customer-billing equipment shows the equipment's
// night-shift rate when one is set (the form's fetch shows the day rate). Display
// only: the server mirrors the same rule on save, and the customer amount on the
// form updates on save. The request already needs level-1 read on Card Equipment,
// which every Card Monthly Card role has. Read-only users are not touched, so their
// form is never marked unsaved.
function card_show_shift_customer_rate(frm, dir, v) {
	if (frm.doc.docstatus !== 0 || !frm.perm[0] || !frm.perm[0].write) return;
	if (!["مؤجَّرة لعميل", "إيجار من الباطن"].includes(dir)) return;
	const night = flt(v.customer_rate_night);
	const rate = frm.doc.shift === "ليلي" && night > 0 ? night : flt(v.customer_rate);
	if (flt(frm.doc.customer_rate) !== rate) frm.set_value("customer_rate", rate);
}

// Mirror of card.card_value.exact_hourly_rate: per hour = rate; per day = rate / daily hours;
// per month = rate / the standard month hours (Card Settings, read through the server).
function card_exact_hourly(v) {
	const rate = flt(v.rate);
	if (v.rate_type === "باليوم")
		return Promise.resolve(flt(v.daily_hours) > 0 ? rate / flt(v.daily_hours) : 0);
	if (v.rate_type === "بالساعة") return Promise.resolve(rate);
	if (v.rate_type === "بالشهر") {
		return frappe
			.call({
				method: "card.card.doctype.card_monthly_card.card_monthly_card.get_standard_month_hours",
				type: "GET",
			})
			.then((r) => {
				// #50: no hard-coded 260. Without the setting the form shows 0 and the server refuses the save
				const month_hours = flt(r && r.message);
				return month_hours > 0 ? rate / month_hours : 0;
			});
	}
	return Promise.resolve(0);
}

// F.7: the card's project follows the assignment covering the card's month
// (client mirror of the server rule — display convenience; the server enforces).
// v3.0.0 (Owner 2026-10-19): the project comes from the approved transports of the
// month. One project: filled in and locked. Moved during the month: only those projects
// can be picked (one card each). The eligible days are kept for building the day rows.
function card_lock_project(frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.equipment) return Promise.resolve();
	const m = parseInt(frm.doc.month);
	const y = parseInt(frm.doc.year);
	if (!m || !y || y < 2000) return Promise.resolve();
	return frappe
		.call({
			method: "card.card.doctype.card_monthly_card.card_monthly_card.get_card_context",
			type: "GET",
			args: {
				equipment: frm.doc.equipment,
				month: frm.doc.month,
				year: frm.doc.year,
				project: frm.doc.project || null,
			},
		})
		.then((r) => {
			const ctx = (r && r.message) || {};
			const projects = ctx.projects || [];
			frm._card_days = new Set(ctx.days || []);
			frm.set_query("project", () => ({ filters: { name: ["in", projects] } }));
			frm.set_df_property("project", "read_only", projects.length <= 1 ? 1 : 0);
			if (projects.length === 1 && frm.doc.project !== projects[0]) {
				return frm.set_value("project", projects[0]);
			}
			if (!projects.length) {
				frappe.msgprint({
					title: __("No transport"),
					indicator: "orange",
					message: __(
						"Equipment {0} has no approved transport to a project in {1}/{2}. Record an Equipment Transport first.",
						[frm.doc.equipment, frm.doc.month, frm.doc.year],
					),
				});
			}
		});
}

function card_calc(frm) {
	if (frm.doc.docstatus !== 0) {
		card_color_fridays(frm);
		return;
	} // never touch submitted/cancelled cards
	let hours = 0,
		work_days = 0,
		billable_stopped = 0,
		stop_only_days = 0;
	(frm.doc.days || []).forEach((r) => {
		if (r.day_status !== "عمل") r.working_hours = 0;
		hours += flt(r.working_hours);
		if (flt(r.working_hours) > 0) work_days++;
		// FR-118: only an explicitly billable stop reason bills its stopped hours
		if (r.stop_reason && cint(r.reason_billable)) {
			billable_stopped += flt(r.stopped_hours);
			if (flt(r.stopped_hours) > 0 && flt(r.working_hours) <= 0) stop_only_days++;
		}
	});
	const billed_hours = hours + billable_stopped;
	let amount = 0;
	if (frm._card_supplier_side) {
		amount =
			frm._card_full_day_rate !== null && frm._card_full_day_rate !== undefined
				? flt((work_days + stop_only_days) * frm._card_full_day_rate, 2)
				: flt(billed_hours * flt(frm._card_hourly), 2);
	}

	// v4: additions / deductions (display only; the server recalculates on save)
	// net_amount is the supplier side, customer_net_amount the customer side; a row
	// without a side takes the card's billed side, as the server does on save (a
	// sub-rental row needs its side, so it counts only once the side is chosen)
	const default_side =
		frm.doc.card_direction === "إيجار من الباطن"
			? null
			: frm.doc.card_direction === "مؤجَّرة لعميل"
			  ? "Customer"
			  : "Supplier";
	let additions = 0,
		deductions = 0;
	const sided = { Supplier: 0, Customer: 0 };
	(frm.doc.adjustments || []).forEach((a) => {
		// a pending owner-paid cash row is recorded but not counted (the server skips it too)
		if (cint(a.is_cash_disbursement) || flt(a.amount) <= 0) return;
		const signed = a.adjustment_type === "إضافة" ? flt(a.amount) : -flt(a.amount);
		if (a.adjustment_type === "إضافة") additions += flt(a.amount);
		else if (a.adjustment_type === "خصم") deductions += flt(a.amount);
		else return;
		// the side net counts a row once its side is known (Supplier or Customer, as on the server)
		const side = a.side || default_side;
		if (side in sided) sided[side] += signed;
	});

	frm.set_value("total_working_hours", hours);
	frm.set_value("billable_stopped_hours", flt(billable_stopped, 2));
	frm.set_value("working_days", work_days);
	frm.set_value("amount", amount);
	frm.set_value("total_additions", flt(additions, 2));
	frm.set_value("total_deductions", flt(deductions, 2));
	frm.set_value("net_amount", flt(amount + sided.Supplier, 2));
	// FR-172: the customer side shows the effect of its rows at once on a saved card. The customer amount
	// itself is the server's (it updates on save), so a new card waits for its first save.
	if (!frm.doc.__islocal) {
		const customer_amount = flt(frm.doc.customer_amount);
		frm.set_value(
			"customer_net_amount",
			customer_amount || sided.Customer ? flt(customer_amount + sided.Customer, 2) : 0,
		);
	}
	frm.refresh_field("days");
	card_color_fridays(frm);
}

function card_check_duplicate(frm) {
	if (!frm.doc.equipment || !frm.doc.month || !frm.doc.year || !frm.doc.shift) return;
	return frappe.db
		.get_list("Card Monthly Card", {
			filters: {
				equipment: frm.doc.equipment,
				month: frm.doc.month,
				year: frm.doc.year,
				shift: frm.doc.shift,
				project: frm.doc.project,
				docstatus: ["!=", 2],
				name: ["!=", frm.doc.name],
			},
			limit: 1,
		})
		.then((r) => {
			if (r.length) {
				frappe.throw(
					__("A {0} card already exists for the same equipment and month: {1}", [
						frm.doc.shift,
						r[0].name,
					]),
				);
			}
		});
}

// Direct read-only link to an EXISTING record (no create affordance). get_form_link
// gives the site-correct URL (fallback for middle-click / new tab); the click is
// handled by card_bind_direct_links → frappe.set_route so it routes in-app (SPA)
// instead of a full page reload, and resolves non-ASCII docnames + permissions natively.
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

// Owner decision 2026-10-14: show the card's equipment, project and lessor (supplier)
// as DIRECT read-only links inside the Connections («الارتباطات») tab — links to the
// EXISTING records only, never a "create new" card (Frappe's native connection cards
// always render a "+ New" button, which the owner rejected).
function card_render_card_links(frm) {
	if (frm.is_new()) return;
	const parts = [];
	if (frm.doc.equipment) {
		parts.push(
			'<div class="mb-2"><span class="text-muted">' +
				__("Equipment") +
				":</span> " +
				card_doc_link("Card Equipment", frm.doc.equipment) +
				"</div>",
		);
	}
	if (frm.doc.project) {
		parts.push(
			'<div class="mb-2"><span class="text-muted">' +
				__("Project") +
				":</span> " +
				card_doc_link("Project", frm.doc.project) +
				"</div>",
		);
	}
	if (frm.doc.ownership !== "ملك" && frm.doc.supplier) {
		parts.push(
			'<div class="mb-2"><span class="text-muted">' +
				__("Supplier") +
				":</span> " +
				card_doc_link("Supplier", frm.doc.supplier) +
				"</div>",
		);
	}
	if (parts.length) {
		card_bind_direct_links(frm.dashboard.add_section(parts.join(""), __("Related records")));
	}
}

// Read-only diesel line: diesel allocated to THIS card's equipment for its
// project + month (owner 2026-10-14). Display only — it NEVER changes net_amount.
// The allocated litres = recorded (direct fills) + estimated (tank fills split
// by card hours, #33); the estimated part is shown as such, never as measured.
function card_render_diesel(frm) {
	if (frm.is_new() || !frm.doc.equipment || !frm.doc.project || !frm.dashboard) return;
	frappe
		.call({ method: "card.diesel.get_card_diesel", args: { card: frm.doc.name }, type: "GET" })
		.then((r) => {
			const d = (r && r.message) || {};
			if (!frm.dashboard) return;
			const line = (label, value) =>
				'<div class="mb-2"><span class="text-muted">' +
				label +
				":</span> " +
				value +
				"</div>";
			// #31: a total that includes an estimate says so; a card with direct fills only keeps the plain labels
			const estimated = flt(d.litres_estimated);
			const parts = [
				line(
					estimated
						? __("Allocated litres (recorded + estimated)")
						: __("Allocated litres"),
					format_number(flt(d.litres), null, 2),
				),
			];
			if (flt(d.litres_estimated)) {
				parts.push(
					line(
						__("Recorded litres (direct fills)"),
						format_number(flt(d.litres_recorded), null, 2),
					),
					line(
						__("Estimated litres (hours split)"),
						format_number(flt(d.litres_estimated), null, 2),
					),
				);
			}
			parts.push(
				line(
					estimated ? __("Diesel cost (incl. estimated)") : __("Diesel cost"),
					format_currency(flt(d.amount)),
				),
			);
			if (flt(d.litres_estimated)) {
				parts.push(
					'<div class="text-muted small">' +
						__("Estimated = project-tank fills split by card hours, not measured.") +
						"</div>",
				);
			}
			if (d.company_bears) {
				parts.push(
					'<div class="text-muted small">' +
						__("Fuel borne by the company — this diesel is our cost.") +
						"</div>",
				);
			}
			parts.push(
				'<div class="text-muted small">' +
					__("Display only — does not affect the rental amount.") +
					"</div>",
			);
			frm.dashboard.add_section(parts.join(""), __("Allocated diesel"));
		});
}

// FR-173: the optional Adjustment type (a type configured in Card Settings) shows only when the card's company has
// such types, or when a row already carries one (an existing value is never hidden or cleared). Otherwise the row is
// entered with Type (Addition or Deduction), Side, Date, Amount and Description; the server still refuses an
// unconfigured type that is sent.
function card_adjustment_classification_hidden(doc) {
	const onload = doc.__onload || {};
	// the type names count only for the company they were built for
	const known = onload.adjustment_types_company === doc.company;
	const configured = known && (onload.adjustment_types || []).length > 0;
	const used = (doc.adjustments || []).some((r) => r.adjustment_type_ref);
	return configured || used ? 0 : 1;
}

function card_toggle_adjustment_classification(frm) {
	// the names are known for the card's company from the server onload (a saved card) or from this read-only call
	// (a new card, or a company change). The state lives on the document, never on the reused form object. A late
	// answer for an earlier company is ignored; a failed call is not remembered, so the next refresh asks again.
	const company = frm.doc.company;
	const onload = frm.doc.__onload || {};
	// a refused or failed call is asked again only after a company change (no repeated error dialog)
	if (
		company &&
		onload.adjustment_types_company !== company &&
		frm.doc.__card_adj_types_pending !== company &&
		frm.doc.__card_adj_types_failed !== company
	) {
		frm.doc.__card_adj_types_pending = company;
		// frappe.xcall: a real Promise that rejects on a server error (frappe.call returns a jQuery deferred)
		frappe
			.xcall(
				"card.card.doctype.card_monthly_card.card_monthly_card.get_adjustment_type_names",
				{ company: company },
				"GET",
			)
			.then((names) => {
				if (frm.doc.company !== company) return;
				frm.doc.__onload = Object.assign({}, frm.doc.__onload, {
					adjustment_types: names || [],
					adjustment_types_company: company,
				});
				card_toggle_adjustment_classification(frm);
			})
			.catch(() => {
				frm.doc.__card_adj_types_failed = company;
			})
			.finally(() => {
				if (frm.doc.__card_adj_types_pending === company)
					frm.doc.__card_adj_types_pending = null;
			});
	}
	const grid = frm.fields_dict.adjustments && frm.fields_dict.adjustments.grid;
	const df = grid && (grid.docfields || []).find((d) => d.fieldname === "adjustment_type_ref");
	if (!df) return;
	const hidden = card_adjustment_classification_hidden(frm.doc);
	if (cint(df.hidden) === hidden) return;
	grid.update_docfield_property("adjustment_type_ref", "hidden", hidden);
	// rebuild the columns: a column saved with "Configure columns" is dropped while its field is hidden
	grid.reset_grid();
}

// #264 part 2 (owner decision 2026-11-24): the Loads column of the days table shows only on a card billed per m³,
// or on a card that already has loads (a stored value is never hidden). The server refuses loads on any other card.
function card_toggle_loads_column(frm) {
	const grid = frm.fields_dict.days && frm.fields_dict.days.grid;
	const df = grid && (grid.docfields || []).find((d) => d.fieldname === "loads_count");
	if (!df) return;
	const used = (frm.doc.days || []).some((r) => cint(r.loads_count));
	const hidden = frm.doc.customer_rate_type === "بالمتر المكعب" || used ? 0 : 1;
	if (cint(df.hidden) === hidden) return;
	grid.update_docfield_property("loads_count", "hidden", hidden);
	// rebuild the columns: a column saved with "Configure columns" is dropped while its field is hidden
	grid.reset_grid();
}

frappe.ui.form.on("Card Monthly Card", {
	setup(frm) {
		// FR-118: only the enabled stop reasons of the card's company
		frm.set_query("stop_reason", "days", () => ({
			filters: { company: frm.doc.company || "", enabled: 1 },
		}));
	},
	refresh(frm) {
		card_color_fridays(frm);
		if (frm.doc.docstatus === 0) card_load_hourly(frm);
		card_lock_project(frm);
		card_render_card_links(frm);
		card_render_diesel(frm);
		card_cash_actions(frm);
		card_cash_status(frm);
		card_toggle_adjustment_classification(frm);
		card_toggle_loads_column(frm);
	},
	company: card_toggle_adjustment_classification,
	customer_rate_type: card_toggle_loads_column,
	equipment(frm) {
		card_load_hourly(frm);
		card_lock_project(frm).then(() => card_build(frm));
	},
	month(frm) {
		card_lock_project(frm).then(() => card_build(frm));
	},
	shift(frm) {
		card_load_hourly(frm);
	},
	year(frm) {
		card_lock_project(frm).then(() => card_build(frm));
	},
	project(frm) {
		// moved during the month: the chosen project decides the eligible days
		if (frm.doc.docstatus !== 0 || !frm.doc.project) return;
		card_lock_project(frm).then(() => {
			const rows = frm.doc.days || [];
			const has_hours = rows.some((r) => flt(r.working_hours));
			if (!has_hours) card_fill_days(frm);
		});
	},
	rate: card_calc,
	rate_type: card_calc,
	validate(frm) {
		card_check_period(frm);
		return card_load_hourly(frm).then(() => {
			card_calc(frm);
			return card_check_duplicate(frm);
		});
	},
});

frappe.ui.form.on("Card Monthly Card Day", {
	working_hours: card_calc,
	day_status: card_calc,
	stopped_hours: card_calc,
	stop_reason(frm, cdt, cdn) {
		// display only: the server re-reads the reason (and its company) on save
		const row = locals[cdt][cdn];
		if (!row.stop_reason) {
			frappe.model.set_value(cdt, cdn, "reason_billable", 0).then(() => card_calc(frm));
			return;
		}
		frappe.db
			.get_value("Card Stop Reason", row.stop_reason, [
				"billable",
				"default_responsible_party_type",
			])
			.then((r) => {
				const v = (r && r.message) || {};
				const updates = [
					frappe.model.set_value(cdt, cdn, "reason_billable", cint(v.billable)),
				];
				if (!row.responsible_party_type && v.default_responsible_party_type) {
					updates.push(
						frappe.model.set_value(
							cdt,
							cdn,
							"responsible_party_type",
							v.default_responsible_party_type,
						),
					);
				}
				return Promise.all(updates);
			})
			.then(() => card_calc(frm));
	},
	days_add: card_color_fridays,
	days_remove: card_calc,
});

frappe.ui.form.on("Card Monthly Card Adjustment", {
	// a new row takes today's date, kept inside the card's period (the server checks it on save)
	adjustments_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.adjustment_date) return;
		let day = frappe.datetime.get_today();
		const start = frm.doc.from_date;
		if (start && day < start) day = start;
		if (frm.doc.to_date && day > frm.doc.to_date) day = frm.doc.to_date;
		frappe.model.set_value(cdt, cdn, "adjustment_date", day);
	},
	adjustment_type: card_calc,
	amount: card_calc,
	side: card_calc,
	is_cash_disbursement: card_calc,
	adjustments_remove(frm) {
		card_calc(frm);
		card_toggle_adjustment_classification(frm);
	},
});

// FR-170: the cash payments of this card, managed from the Additions & Deductions table. Each cash row shows its payment
// status and journal entry in the table; the actions for a row's payment sit on this card. Every action calls a server
// method that checks the role, the company and the state again: hiding a button is not the control.
const CASH_MANAGER_ROLES = ["Card Manager", "System Manager"];

function cash_row_label(frm, child_name) {
	const a = (frm.doc.adjustments || []).find((x) => x.name === child_name);
	if (!a) return null;
	const amount = format_currency(a.amount, frm.doc.currency);
	return `${a.idx}. ${frappe.datetime.str_to_user(a.adjustment_date) || ""} · ${amount} · ${
		a.description || ""
	}`;
}

// The payments the user can act on: only the latest payment of each cash row (an earlier cancelled one is superseded),
// and only a row that still exists on the card.
function cash_actionable(frm, payments) {
	const latest = {};
	payments.forEach((p) => {
		latest[p.adjustment_row] = p;
	});
	return Object.values(latest).filter((p) => cash_row_label(frm, p.adjustment_row) !== null);
}

// A dialog that stays open when the server refuses, so the typed values are kept. (frappe.prompt hides its dialog
// before the callback runs, which would lose them.)
function cash_dialog(title, fields, primary_label, on_submit) {
	const dialog = new frappe.ui.Dialog({
		title,
		fields,
		primary_action_label: primary_label,
		primary_action: (values) => on_submit(values, dialog),
	});
	dialog.show();
	return dialog;
}

// One payment: the dialog for it. Several: the user picks the payment by its row label (the label carries the payment
// name, so two payments never collapse into one option).
function cash_pick_payment(frm, payments, title, primary, run) {
	if (payments.length === 1) return run(payments[0], null);
	const by_label = {};
	payments.forEach((p) => {
		by_label[
			p.name
				? `${cash_row_label(frm, p.adjustment_row)} · ${p.name}`
				: cash_row_label(frm, p.adjustment_row)
		] = p;
	});
	const options = Object.keys(by_label);
	return cash_dialog(
		title,
		[
			{
				label: __("Cash row"),
				fieldname: "row",
				fieldtype: "Select",
				options: options.join("\n"),
				default: options[0],
				reqd: 1,
			},
		],
		primary,
		(values, dialog) => run(by_label[values.row], dialog),
	);
}

// The table's status columns: display only (set in memory, never saved as a change; the server refreshes them on save).
function card_cash_status(frm) {
	if (frm.is_new()) return;
	frappe.call({
		method: "card.cash_disbursement.get_cash_row_status",
		type: "GET", // read-only endpoint; a default POST is refused with "Not permitted"
		args: { card: frm.doc.name },
		callback: (r) => {
			const info = r.message || {};
			(frm.doc.adjustments || []).forEach((row) => {
				const s = info[row.name];
				if (!s) return;
				row.cash_status = s.label;
				row.cash_payment = s.name;
				row.cash_journal_entry = s.journal_entry;
			});
			frm.refresh_field("adjustments");
		},
	});
}

function card_cash_actions(frm) {
	if (frm.is_new()) return;
	const cash_rows = (frm.doc.adjustments || []).filter((a) => cint(a.is_cash_disbursement));
	const is_manager = CASH_MANAGER_ROLES.some((r) => frappe.user_roles.includes(r));
	frappe.call({
		method: "card.cash_disbursement.get_cash_disbursements",
		type: "GET",
		args: { card: frm.doc.name },
		callback: (r) => {
			const payments = cash_actionable(frm, r.message || []);
			const requestable = cash_rows.filter(
				(a) => !payments.some((p) => p.adjustment_row === a.name),
			);
			if (frm.doc.docstatus === 0 && requestable.length) {
				frm.add_custom_button(
					__("Request cash approval"),
					() =>
						cash_pick_payment(
							frm,
							requestable.map((a) => ({ adjustment_row: a.name, name: null })),
							__("Request cash approval"),
							__("Request"),
							(payment, dialog) =>
								cash_dialog(
									__("Request cash approval"),
									[
										{
											label: __("Payment date"),
											fieldname: "payment_date",
											fieldtype: "Date",
											default: frappe.datetime.get_today(),
											reqd: 1,
										},
										{
											label: __("Evidence (receipt number or reference)"),
											fieldname: "evidence",
											fieldtype: "Data",
											reqd: 1,
										},
									],
									__("Request"),
									(values, d) =>
										frappe.call({
											method: "card.cash_disbursement.request_cash_disbursement",
											args: {
												card: frm.doc.name,
												row: payment.adjustment_row,
												payment_date: values.payment_date,
												evidence: values.evidence,
											},
											freeze: true,
											callback: () => {
												d.hide();
												if (dialog) dialog.hide();
												frappe.show_alert({
													message: __("Cash approval requested"),
													indicator: "green",
												});
												frm.reload_doc();
											},
										}),
								),
						),
					__("Cash payments"),
				);
			}

			const with_status = (status) => payments.filter((p) => p.status === status);
			// every action below is a manager action: the menu is shown to Card Manager and System Manager only
			if (!is_manager) return;
			const run_simple = (method, done) => (payment, dialog) =>
				frappe.call({
					method,
					args: { name: payment.name },
					freeze: true,
					callback: () => {
						if (dialog) dialog.hide();
						frappe.show_alert({ message: done, indicator: "green" });
						frm.reload_doc();
					},
				});
			const pending = with_status("Pending");
			if (pending.length) {
				frm.add_custom_button(
					__("Approve cash payment"),
					() =>
						cash_pick_payment(
							frm,
							pending,
							__("Approve cash payment"),
							__("Approve"),
							(payment, dialog) =>
								frappe.confirm(
									__(
										"Approve this cash payment? The approver must not be the requester.",
									),
									() =>
										run_simple(
											"card.cash_disbursement.approve_cash_disbursement",
											__("Cash payment approved"),
										)(payment, dialog),
								),
						),
					__("Cash payments"),
				);
			}
			const approved = [...with_status("Approved"), ...with_status("Posting Failed")];
			if (approved.length) {
				frm.add_custom_button(
					__("Queue cash for posting"),
					() =>
						cash_pick_payment(
							frm,
							approved,
							__("Queue cash for posting"),
							__("Queue"),
							run_simple(
								"card.cash_disbursement.queue_posting",
								__("Cash payment queued for posting"),
							),
						),
					__("Cash payments"),
				);
			}
			// a posted payment gets a cancellation request; an approved or failed one that was never posted is cancelled
			// directly with its reason (no journal entry exists)
			const posted = [...with_status("Posted"), ...approved.filter((p) => !p.journal_entry)];
			if (posted.length) {
				frm.add_custom_button(
					__("Request cash cancellation"),
					() =>
						cash_pick_payment(
							frm,
							posted,
							__("Request cash cancellation"),
							__("Request"),
							(payment, dialog) =>
								cash_dialog(
									__("Request cash cancellation"),
									[
										{
											label: __("Reason"),
											fieldname: "reason",
											fieldtype: "Small Text",
											reqd: 1,
										},
									],
									__("Request"),
									(values, d) =>
										frappe.call({
											method: "card.cash_disbursement.request_cancellation",
											args: { name: payment.name, reason: values.reason },
											freeze: true,
											callback: () => {
												d.hide();
												if (dialog) dialog.hide();
												frappe.show_alert({
													message: __("Cancellation requested"),
													indicator: "green",
												});
												frm.reload_doc();
											},
										}),
								),
						),
					__("Cash payments"),
				);
			}
			const replaceable = with_status("Cancelled").filter((p) => !p.replacement_pending);
			if (replaceable.length) {
				frm.add_custom_button(
					__("Request cash replacement"),
					() =>
						cash_pick_payment(
							frm,
							replaceable,
							__("Request cash replacement"),
							__("Request"),
							(payment, dialog) =>
								cash_dialog(
									__("Request cash replacement"),
									[
										{
											label: __("Reason"),
											fieldname: "reason",
											fieldtype: "Small Text",
											reqd: 1,
										},
										{
											label: __("Payment date"),
											fieldname: "payment_date",
											fieldtype: "Date",
											default: frappe.datetime.get_today(),
											reqd: 1,
										},
										{
											label: __("Evidence (receipt number or reference)"),
											fieldname: "evidence",
											fieldtype: "Data",
											reqd: 1,
										},
									],
									__("Request"),
									(values, d) =>
										frappe.call({
											method: "card.cash_disbursement.request_replacement",
											args: {
												name: payment.name,
												reason: values.reason,
												payment_date: values.payment_date,
												evidence: values.evidence,
											},
											freeze: true,
											callback: () => {
												d.hide();
												if (dialog) dialog.hide();
												frappe.show_alert({
													message: __("Replacement requested"),
													indicator: "green",
												});
												frm.reload_doc();
											},
										}),
								),
						),
					__("Cash payments"),
				);
			}
		},
	});
}
