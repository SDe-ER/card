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
	for (let d = 1; d <= last; d++) {
		const dt = new Date(y, m - 1, d);
		const row = frm.add_child("days");
		row.operation_date = `${y}-${card_pad(m)}-${card_pad(d)}`;
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

// Hourly rate comes from the equipment (approved_hourly_rate, computed by Server Script
// "Card Equipment - Hourly Rate"). Display only: the server recalculates on save.
function card_load_hourly(frm) {
	if (!frm.doc.equipment) {
		frm._card_hourly = 0;
		frm._card_owned = false;
		return Promise.resolve();
	}
	return frappe.db
		.get_value("Card Equipment", frm.doc.equipment, ["approved_hourly_rate", "ownership"])
		.then((r) => {
			const v = (r && r.message) || {};
			frm._card_hourly = flt(v.approved_hourly_rate);
			frm._card_owned = v.ownership === "ملك";
			card_calc(frm);
		});
}

function card_calc(frm) {
	if (frm.doc.docstatus !== 0) {
		card_color_fridays(frm);
		return;
	} // never touch submitted/cancelled cards
	let hours = 0,
		work_days = 0;
	(frm.doc.days || []).forEach((r) => {
		if (r.day_status !== "عمل") r.working_hours = 0;
		hours += flt(r.working_hours);
		if (flt(r.working_hours) > 0) work_days++;
	});
	const amount = frm._card_owned ? 0 : flt(hours * flt(frm._card_hourly), 2);

	// v4: additions / deductions (display only; the server recalculates on save)
	let additions = 0,
		deductions = 0;
	(frm.doc.adjustments || []).forEach((a) => {
		if (a.adjustment_type === "إضافة") additions += flt(a.amount);
		else if (a.adjustment_type === "خصم") deductions += flt(a.amount);
	});

	frm.set_value("total_working_hours", hours);
	frm.set_value("working_days", work_days);
	frm.set_value("amount", amount);
	frm.set_value("total_additions", flt(additions, 2));
	frm.set_value("total_deductions", flt(deductions, 2));
	frm.set_value("net_amount", flt(amount + additions - deductions, 2));
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
				docstatus: ["!=", 2],
				name: ["!=", frm.doc.name],
			},
			limit: 1,
		})
		.then((r) => {
			if (r.length) {
				frappe.throw(__("A {0} card already exists for the same equipment and month: {1}", [frm.doc.shift, r[0].name]));
			}
		});
}

// Direct read-only link to an EXISTING record (no create affordance).
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
		frm.dashboard.add_section(parts.join(""), __("Related records"));
	}
}

frappe.ui.form.on("Card Monthly Card", {
	refresh(frm) {
		card_color_fridays(frm);
		if (frm.doc.docstatus === 0) card_load_hourly(frm);
		card_render_card_links(frm);
	},
	equipment: card_load_hourly,
	month: card_build,
	year: card_build,
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
	days_add: card_color_fridays,
	days_remove: card_calc,
});

frappe.ui.form.on("Card Monthly Card Adjustment", {
	adjustment_type: card_calc,
	amount: card_calc,
	adjustments_remove: card_calc,
});
