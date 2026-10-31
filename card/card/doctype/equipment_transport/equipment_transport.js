// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

// v3.0.0 (Owner 2026-10-19): the user picks ownership -> supplier -> the supplier's
// equipment -> project; the server reads the kind of move from each machine's history.
// The equipment link keeps frappe's own "Create a new Card Equipment" entry for a
// machine that is not registered yet.
frappe.ui.form.on("Equipment Transport", {
	setup(frm) {
		frm.set_query("card_equipment", "items", () => {
			const filters = { company: frm.doc.company || undefined };
			if (frm.doc.ownership) filters.ownership = frm.doc.ownership;
			if (frm.doc.equipment_supplier) filters.supplier = frm.doc.equipment_supplier;
			return { filters };
		});
		frm.set_query("cost_project", () => ({
			filters: { company: frm.doc.company || undefined },
		}));
		frm.set_query("overhead_cost_center", () => ({
			filters: { company: frm.doc.company || undefined, is_group: 0, disabled: 0 },
		}));
	},
	refresh(frm) {
		// P1-2: the cost project is chosen explicitly; the origin and destination are only offered
		if (
			frm.doc.docstatus === 0 &&
			frm.doc.responsibility === "Company bears the cost" &&
			!["Workshop", "Storage"].includes(frm.doc.destination_type)
		) {
			const offer = [
				[
					__("Destination project"),
					frm.doc.destination_type === "Project" ? frm.doc.project : null,
				],
				[__("Source project"), frm.doc.source_project],
			];
			for (const [label, project] of offer) {
				if (project) {
					frm.add_custom_button(
						`${label}: ${project}`,
						() => frm.set_value("cost_project", project),
						__("Use as cost project"),
					);
				}
			}
		}
		if (
			frm.doc.docstatus === 1 &&
			frm.doc.financial_status === "Pending" &&
			frappe.user.has_role("Accounts Manager")
		) {
			frm.add_custom_button(__("Record financial decision"), () =>
				card_financial_decision(frm),
			);
		}
	},
	onload(frm) {
		// v4.1.2: one company only: fill it and keep it out of the way (the server still
		// validates it); with several companies the user picks one as before
		frappe.call({ method: "card.api.get_only_company", type: "GET" }).then(async (r) => {
			const only = r && r.message;
			if (!only) return;
			if (frm.is_new() && !frm.doc.company) await frm.set_value("company", only);
			if (frm.doc.company === only) frm.toggle_display("company", false);
		});
	},
	ownership(frm) {
		if (frm.doc.ownership === "ملك" && frm.doc.equipment_supplier) {
			frm.set_value("equipment_supplier", null);
		}
	},
});

// "From" is never typed: show where the machine is now as soon as it is picked
// (the server recomputes it on save from the last approved move).
frappe.ui.form.on("Equipment Transport Item", {
	card_equipment(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.card_equipment) return;
		frappe
			.call({
				method: "card.card.doctype.equipment_transport.equipment_transport.get_equipment_location",
				type: "GET",
				args: { equipment: row.card_equipment },
			})
			.then((r) => {
				const here = (r && r.message) || {};
				frappe.model.set_value(cdt, cdn, {
					from_type: here.type || "Storage",
					from_project: here.project || null,
					from_location: here.location || null,
				});
				// the header "From" follows the first machine
				if (row.idx === 1) {
					frm.set_value({
						source_type: here.type || "Storage",
						source_project: here.project || null,
						source_location: here.location || null,
					});
				}
			});
	},
});

// P1-2 (Owner D3/D6/D7/D8; input simplification 2026-10-31): an Accounts Manager records the
// financial decision of a submitted transport with the fewest inputs; the server checks the role, the
// company, that the user did not create, edit or submit it, and the confirmation of the customer.
function card_financial_decision(frm) {
	const decisions = {
		Customer: ["Bill customer", "Company absorbs", "Return for correction"],
		"Equipment Supplier": ["Recover from equipment supplier", "Return for correction"],
	}[frm.doc.cost_bearer] || ["Return for correction"];
	const when = (decision) => `eval:doc.decision=="${decision}"`;
	const dialog = new frappe.ui.Dialog({
		title: __("Record financial decision"),
		fields: [
			{
				fieldname: "decision",
				label: __("Cost decision"),
				fieldtype: "Select",
				options: decisions.map((d) => ({ value: d, label: __(d) })),
				reqd: 1,
			},
			{
				fieldname: "billing_project",
				label: __("Billing project"),
				fieldtype: "Link",
				options: "Project",
				get_query: () => ({ filters: { company: frm.doc.company } }),
				depends_on: when("Bill customer"),
				mandatory_depends_on: when("Bill customer"),
				onchange: () => card_fill_project_customer(dialog, frm),
			},
			{
				// filled from the billing project's own customer; typed only when the project has none
				fieldname: "customer",
				label: __("Customer"),
				fieldtype: "Link",
				options: "Customer",
				depends_on: when("Bill customer"),
				mandatory_depends_on: when("Bill customer"),
				onchange: () => dialog.set_value("confirmed", 0),
			},
			{
				fieldname: "billing_amount",
				label: __("Agreed billing amount (before VAT)"),
				fieldtype: "Currency",
				depends_on: when("Bill customer"),
				mandatory_depends_on: when("Bill customer"),
			},
			{
				fieldname: "billing_reference",
				label: __("Authorization reference"),
				fieldtype: "Data",
				depends_on: when("Bill customer"),
				mandatory_depends_on: when("Bill customer"),
			},
			{
				fieldname: "confirmed",
				label: __("I confirmed the customer and the billing project"),
				fieldtype: "Check",
				depends_on: when("Bill customer"),
			},
			{
				fieldname: "absorption_reason",
				label: __("Absorption reason"),
				fieldtype: "Small Text",
				depends_on: when("Company absorbs"),
				mandatory_depends_on: when("Company absorbs"),
			},
			{
				fieldname: "recovery_amount",
				label: __("Recovery amount"),
				fieldtype: "Currency",
				depends_on: when("Recover from equipment supplier"),
				mandatory_depends_on: when("Recover from equipment supplier"),
			},
			{
				fieldname: "note",
				label: __("Decision note"),
				fieldtype: "Small Text",
				depends_on: when("Return for correction"),
				mandatory_depends_on: when("Return for correction"),
			},
			{
				fieldname: "more_section",
				label: __("More decision details"),
				fieldtype: "Section Break",
				collapsible: 1,
				depends_on: 'eval:doc.decision && doc.decision!="Return for correction"',
			},
			{
				fieldname: "billing_mode",
				label: __("Customer invoicing method"),
				fieldtype: "Select",
				options: [
					{ value: "Monthly invoice", label: __("Monthly invoice") },
					{ value: "Separate invoice", label: __("Separate invoice") },
				],
				default: "Monthly invoice",
				depends_on: when("Bill customer"),
			},
			{
				fieldname: "billing_document",
				label: __("Authorization document"),
				fieldtype: "Attach",
				depends_on: when("Bill customer"),
				mandatory_depends_on: 'eval:doc.decision=="Bill customer" && doc.billing_mode=="Separate invoice"',
			},
			{
				fieldname: "recovery_mode",
				label: __("Recovery method"),
				fieldtype: "Select",
				options: [
					{ value: "Deduct from monthly dues", label: __("Deduct from monthly dues") },
					{ value: "Adjustment document", label: __("Adjustment document") },
				],
				default: "Deduct from monthly dues",
				depends_on: when("Recover from equipment supplier"),
			},
			{
				fieldname: "other_note",
				label: __("Decision note"),
				fieldtype: "Small Text",
			},
		],
		primary_action_label: __("Record decision"),
		primary_action(values) {
			const { other_note, note, ...rest } = values;
			frappe
				.call({
					method: "card.card.doctype.equipment_transport.equipment_transport.record_financial_decision",
					type: "POST",
					args: { transport: frm.doc.name, ...rest, note: note || other_note },
					freeze: true,
				})
				.then(() => {
					dialog.hide();
					frm.reload_doc();
				});
		},
	});
	dialog.show();
	// suggested only when the transport's project names a customer in its project record;
	// the accountant confirms the customer and the project before recording
	card_billing_customer(frm, null).then((s) => {
		if (s.project) dialog.set_value("billing_project", s.project);
	});
}

function card_billing_customer(frm, project) {
	return frappe
		.call({
			method: "card.card.doctype.equipment_transport.equipment_transport.billing_customer",
			type: "GET",
			args: { transport: frm.doc.name, project },
		})
		.then((r) => (r && r.message) || {});
}

function card_fill_project_customer(dialog, frm) {
	const project = dialog.get_value("billing_project");
	dialog.set_value("confirmed", 0);
	if (!project) return;
	card_billing_customer(frm, project).then((s) => {
		if (s.customer) dialog.set_value("customer", s.customer);
	});
}
