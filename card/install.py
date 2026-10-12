# Copyright (c) 2026, Ahmed Shehab and contributors
# For license information, please see license.txt
"""Install-time automation for the CARD app.

These hooks make ``bench install-app card`` + ``bench migrate`` fully
self-contained on any target site: a fresh site, or one that already
carries the legacy production-native CARD custom config (a custom Module
Def "Card", custom=1 DocTypes, the legacy Server/Client Scripts, and a
legacy standard=0 "Card" Desktop Icon).

No manual step is required on the target site. Every function is
idempotent and is a safe no-op when there is nothing to adopt, so a fresh
install and an in-place re-run behave identically.
"""

import frappe

APP_NAME = "card"
MODULE = "Card"

CARD_DOCTYPES = (
	"Card Equipment",
	"Card Equipment Assignment",
	"Card Equipment Category",
	"Card Equipment Supplier",
	"Card Equipment Type",
	"Card Monthly Card",
	"Card Monthly Card Adjustment",
	"Card Monthly Card Day",
)

CMC_DOCTYPE = "Card Monthly Card"
CMC_DEFAULT_PRINT_FORMAT = "كارت تشغيل شهري"

# The app-native Desk launcher ("Card appears on the Desk immediately after
# install"). Shipped as an app-owned STANDARD Desktop Icon (file-backed at
# card/desktop_icon/card.json so migrate's orphan-prune keeps it) linking to
# the Card Workspace Sidebar, with the official logo.
DESK_ICON_LABEL = "Card"
CARD_LOGO_URL = "/assets/card/images/card-logo.svg"

# Legacy logic is ported to the app controllers (card.api +
# card/<doctype>/<doctype>.py). The original Server/Client Scripts are
# disabled (never deleted) so the controllers are the single source of
# truth while the scripts remain available for an audit comparison.
LEGACY_SERVER_SCRIPTS = (
	"Card Equipment Supplier - Sync on Cancel",
	"Card Equipment Supplier - Sync on Submit",
	"Card Equipment Supplier - Refresh",
	"Card Equipment - Hourly Rate",
	"Card Monthly Card - Validate",
)

LEGACY_CLIENT_SCRIPTS = (
	"Card Equipment Supplier - Buttons",
	"Card Monthly Card - Days and Totals",
)


def before_install():
	"""Run before the app's DocTypes/entities are synced by install-app.

	Adopts any pre-existing legacy CARD config so the standard app files
	sync onto the existing tables/records with no data loss and no
	collision.
	"""
	_adopt_module_def()
	_adopt_doctypes()
	_ensure_card_desk_icon()
	frappe.db.commit()


def after_install():
	"""Run after the app's entities are synced. Reconciles the remaining
	post-sync invariants (print default, disabled legacy scripts, single
	Desk launcher)."""
	_reconcile()
	frappe.db.commit()


def _reconcile():
	"""Idempotent post-install reconciliation. Shared by after_install and
	the v1_0 migration patch so the install hook and the patch can never
	drift apart."""
	_ensure_print_default_property_setter()
	disable_legacy_scripts()
	_ensure_card_desk_icon()


def _adopt_module_def():
	"""Re-point an existing Module Def "Card" to this app WITHOUT deleting it.

	A legacy install owns it as a custom module (``app_name != "card"``);
	hand it to the app so install-app does not raise DuplicateEntryError.
	Never force-deletes a row (safe for a production target).
	"""
	if not frappe.db.exists("Module Def", MODULE):
		return
	current = frappe.db.get_value("Module Def", MODULE, ["app_name", "custom"], as_dict=True)
	if current.app_name != APP_NAME or current.custom:
		frappe.db.set_value(
			"Module Def",
			MODULE,
			{"app_name": APP_NAME, "custom": 0},
			update_modified=False,
		)


def _adopt_doctypes():
	"""Flip any pre-existing legacy CARD DocType to app-owned.

	Sets ``custom=0`` and ``module=Card`` so the standard JSON sync updates
	the existing table instead of colliding with a custom definition. Also
	clears the stray DocType-level ``default_print_format`` (a standard
	DocType may not carry it on the row; the Property Setter created in
	``after_install`` provides the print default instead).
	"""
	for dt in CARD_DOCTYPES:
		if not frappe.db.exists("DocType", dt):
			continue
		current = frappe.db.get_value("DocType", dt, ["custom", "module"], as_dict=True)
		updates = {}
		if current.custom:
			updates["custom"] = 0
		if current.module != MODULE:
			updates["module"] = MODULE
		if updates:
			frappe.db.set_value("DocType", dt, updates, update_modified=False)

	if frappe.db.exists("DocType", CMC_DOCTYPE) and frappe.db.get_value(
		"DocType", CMC_DOCTYPE, "default_print_format"
	):
		frappe.db.set_value(
			"DocType", CMC_DOCTYPE, "default_print_format", None, update_modified=False
		)


def _ensure_print_default_property_setter():
	"""Idempotently provide Card Monthly Card's default print format via a
	Property Setter (the Customize-Form mechanism), so the print default is
	identical after install on both fresh and legacy sites.
	"""
	if not frappe.db.exists("DocType", CMC_DOCTYPE):
		return
	if frappe.db.exists(
		"Property Setter",
		{
			"doc_type": CMC_DOCTYPE,
			"doctype_or_field": "DocType",
			"property": "default_print_format",
		},
	):
		return
	ps = frappe.new_doc("Property Setter")
	ps.doctype_or_field = "DocType"
	ps.doc_type = CMC_DOCTYPE
	ps.property = "default_print_format"
	ps.property_type = "Data"
	ps.value = CMC_DEFAULT_PRINT_FORMAT
	ps.insert(ignore_permissions=True)


def _ensure_card_desk_icon():
	"""Guarantee exactly ONE app-owned Desk launcher for Card.

	- Adopts/replaces any pre-existing (legacy standard=0, Administrator-
	  owned) "Card" Desktop Icon so a normal System Manager also sees it and
	  it carries the official logo — never leaving two icons.
	- On a fresh site the icon also arrives from card/desktop_icon/card.json
	  during sync; this keeps it correct and deduplicated regardless of
	  order. Link validation is bypassed because the Card Workspace Sidebar
	  may sync after this runs.
	"""
	existing = frappe.get_all("Desktop Icon", filters={"label": DESK_ICON_LABEL}, pluck="name")
	for extra in existing[1:]:
		frappe.delete_doc("Desktop Icon", extra, force=1, ignore_permissions=True)

	fields = {
		"standard": 1,
		"app": APP_NAME,
		"icon_type": "Link",
		"link_type": "Workspace Sidebar",
		"link_to": MODULE,
		"logo_url": CARD_LOGO_URL,
		"hidden": 0,
	}
	if existing:
		frappe.db.set_value("Desktop Icon", existing[0], fields, update_modified=False)
	else:
		icon = frappe.new_doc("Desktop Icon")
		icon.label = DESK_ICON_LABEL
		for key, value in fields.items():
			setattr(icon, key, value)
		icon.flags.ignore_links = True
		icon.flags.ignore_mandatory = True
		icon.insert(ignore_permissions=True)


def disable_legacy_scripts():
	"""Disable (never delete) the legacy Server/Client Scripts.

	Idempotent: only writes rows that are not already disabled. Shared by
	``after_install`` and the ``v1_0`` migration patch.
	"""
	for name in LEGACY_SERVER_SCRIPTS:
		if frappe.db.exists("Server Script", name) and frappe.db.get_value(
			"Server Script", name, "disabled"
		) != 1:
			frappe.db.set_value("Server Script", name, "disabled", 1, update_modified=False)

	for name in LEGACY_CLIENT_SCRIPTS:
		if frappe.db.exists("Client Script", name) and frappe.db.get_value(
			"Client Script", name, "enabled"
		) != 0:
			frappe.db.set_value("Client Script", name, "enabled", 0, update_modified=False)
