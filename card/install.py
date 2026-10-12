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

import json

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
	_append_card_to_user_layouts()


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


def _user_can_see_card(user):
	"""Whether ``user`` is entitled to the Card launcher.

	Administrator always qualifies. Otherwise the Card Desktop Icon's own
	role restriction decides: if it carries explicit roles, the user must
	hold one of them; if it is unrestricted, fall back to the "System
	Manager" role (the production CARD audience).
	"""
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	icon_roles = frappe.get_all(
		"Has Role", filters={"parenttype": "Desktop Icon", "parent": DESK_ICON_LABEL}, pluck="role"
	)
	if icon_roles:
		return bool(roles & set(icon_roles))
	return "System Manager" in roles


def _is_card_layout_entry(item):
	"""True if a Desktop Layout entry is the Card launcher (any shape the
	legacy adopted icon or an earlier run may have left)."""
	if not isinstance(item, dict):
		return False
	return (
		item.get("name") == MODULE
		or item.get("label") == DESK_ICON_LABEL
		or (item.get("link_to") == MODULE and item.get("icon_type") == "Link")
	)


def _card_layout_entry(existing_items):
	"""Build the Card grid entry from the app-owned Desktop Icon so its shape
	matches every other entry. Placed at the end (max idx + 1)."""
	icon = frappe.db.get_value(
		"Desktop Icon",
		DESK_ICON_LABEL,
		["label", "icon_type", "link_type", "link_to", "app", "icon", "logo_url", "bg_color", "standard", "restrict_removal"],
		as_dict=True,
	)
	max_idx = max([i.get("idx", 0) for i in existing_items if isinstance(i, dict)] + [-1])
	return {
		"label": icon.label,
		"bg_color": icon.bg_color,
		"link": None,
		"link_type": icon.link_type,
		"app": icon.app,
		"icon_type": icon.icon_type,
		"parent_icon": None,
		"icon": icon.icon,
		"link_to": icon.link_to,
		"idx": max_idx + 1,
		"standard": icon.standard,
		"logo_url": icon.logo_url,
		"hidden": 0,
		"name": DESK_ICON_LABEL,
		"restrict_removal": icon.restrict_removal or 0,
	}


def _append_card_to_user_layouts():
	"""Reconcile the Card launcher in every existing per-user Desktop Layout
	(append-only, option B).

	A user whose saved Desk grid predates Card would never see the standard
	Card icon (the grid is driven by their stored layout, not the icon
	table). For each layout:

	- if it does NOT contain a Card entry and the owner is entitled to Card,
	  the Card entry is appended at the END — nothing else is reordered;
	- if it ALREADY contains a Card entry (incl. the legacy adopted one), it
	  is never duplicated and never reordered; only that entry's ``logo_url``
	  is backfilled to the official logo when missing, so the icon always
	  renders with the logo. No other entry and no other field is touched.

	Idempotent; the list of updated users is logged.
	"""
	if not frappe.db.exists("DocType", "Desktop Layout"):
		return []
	if not frappe.db.exists("Desktop Icon", DESK_ICON_LABEL):
		return []

	updated = []
	for name in frappe.get_all("Desktop Layout", pluck="name"):
		user = frappe.db.get_value("Desktop Layout", name, "user")
		if not user:
			continue
		raw = frappe.db.get_value("Desktop Layout", name, "layout")
		try:
			items = json.loads(raw) if raw else []
		except (ValueError, TypeError):
			continue
		if not isinstance(items, list):
			continue

		card_positions = [i for i, it in enumerate(items) if _is_card_layout_entry(it)]
		changed = False
		if card_positions:
			# Present already: never add a second one, never reorder, never
			# touch any other entry — only backfill the official logo.
			entry = items[card_positions[0]]
			if entry.get("logo_url") != CARD_LOGO_URL:
				entry["logo_url"] = CARD_LOGO_URL
				changed = True
		elif _user_can_see_card(user):
			items.append(_card_layout_entry(items))
			changed = True

		if changed:
			frappe.db.set_value("Desktop Layout", name, "layout", json.dumps(items), update_modified=False)
			updated.append(user)

	if updated:
		frappe.logger("card").info("card: reconciled Card launcher in Desktop Layouts: %s" % updated)
	return updated


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
