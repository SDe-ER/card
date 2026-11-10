// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
// FR-142: verify, approve or return a submitted daily log. The buttons only save approval_status (and the
// reason); the server (card.daily_log.check_transition) decides who may do it, whether the company asks for the
// supervisor step, and writes every approval field.
// FR-145: on an approved log, "Generate monthly cards" creates or updates the DRAFT monthly cards of the log's
// project and month from every approved log (card.daily_log_generation.generate_monthly_cards, POST; the server
// checks the permission and the company, and never submits a card).

const PENDING = "Pending";
const VERIFIED = "Verified by supervisor";

frappe.ui.form.on("Card Daily Log", {
	refresh(frm) {
		const status = frm.doc.approval_status;
		if (
			frm.doc.docstatus === 1 &&
			status === "Approved" &&
			frappe.model.can_create("Card Monthly Card")
		) {
			frm.add_custom_button(__("Generate monthly cards"), () => generate_monthly_cards(frm));
		}
		if (frm.doc.docstatus !== 1 || ![PENDING, VERIFIED].includes(status)) return;
		const approver = frappe.user.has_role(["Card Manager", "System Manager"]);
		const supervisor = frappe.user.has_role("Card Supervisor");
		const set_status = (value) => {
			frm.set_value("approval_status", value);
			frm.save("Update");
		};
		if (supervisor && status === PENDING) {
			frm.add_custom_button(__("Verify daily log"), () => set_status(VERIFIED));
		}
		if (approver) {
			frm.add_custom_button(__("Approve daily log"), () => set_status("Approved"));
		}
		if (approver || (supervisor && status === PENDING)) {
			frm.add_custom_button(__("Return daily log"), () => {
				frappe.prompt(
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("Daily log return reason"),
						reqd: 1,
					},
					(values) => {
						frm.set_value("return_reason", values.reason);
						set_status("Returned for correction");
					},
					__("Return daily log"),
				);
			});
		}
	},
});

function generate_monthly_cards(frm) {
	frappe.confirm(
		__(
			"Create or update the draft monthly cards of project {0} for the month of {1} from the approved daily logs? Submitted cards are not changed.",
			[frm.doc.project, frappe.datetime.str_to_user(frm.doc.log_date)],
		),
		() => {
			frappe.call({
				method: "card.daily_log_generation.generate_monthly_cards",
				type: "POST",
				args: {
					company: frm.doc.company,
					project: frm.doc.project,
					month: frm.doc.log_date,
				},
				freeze: true,
				freeze_message: __("Generating monthly cards"),
				callback: (r) => show_generation_result(r.message || {}),
			});
		},
	);
}

function show_generation_result(result) {
	const esc = frappe.utils.escape_html;
	const links = (names) =>
		(names || [])
			.map(
				(name) =>
					`<a href="/app/card-monthly-card/${encodeURIComponent(name)}">${esc(
						name,
					)}</a>`,
			)
			.join(", ") || "-";
	const reasons = {
		off_project: __("not on the project that day"),
		unit_component: __("component of a unit that day"),
	};
	const lines = [
		`<p><b>${__("Cards created")}:</b> ${links(result.created)}</p>`,
		`<p><b>${__("Cards updated")}:</b> ${links(result.updated)}</p>`,
		`<p><b>${__("Cards unchanged")}:</b> ${links(result.unchanged)}</p>`,
		`<p><b>${__("Submitted cards not changed")}:</b> ${links(result.kept_submitted)}</p>`,
	];
	if ((result.skipped_days || []).length) {
		const items = result.skipped_days
			.map(
				(d) =>
					`<li>${esc(d.equipment)} ${esc(d.date)}: ${esc(
						reasons[d.reason] || d.reason,
					)}</li>`,
			)
			.join("");
		lines.push(`<p><b>${__("Days left out")}:</b></p><ul>${items}</ul>`);
	}
	if ((result.errors || []).length) {
		const items = result.errors
			.map((e) => `<li>${esc(e.equipment)} (${esc(__(e.shift))}): ${esc(e.message)}</li>`)
			.join("");
		lines.push(`<p><b>${__("Cards not saved")}:</b></p><ul>${items}</ul>`);
	}
	frappe.msgprint({
		title: __("Monthly cards from daily logs"),
		message: lines.join(""),
		indicator: (result.errors || []).length ? "orange" : "green",
	});
}
