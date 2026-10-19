# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
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
from frappe.model.rename_doc import rename_doc as _rename_doc
from frappe.utils import now

APP_NAME = "card"
MODULE = "Card"
# Legacy Module Def left by the original in-site customization (the app ships
# only MODULE in modules.txt). Retired idempotently by _retire_legacy_custom_module().
LEGACY_MODULE = "Card (Custom)"
# Child/meta columns never copied when cloning a Sidebar Item row at DB level.
_SIDEBAR_CHILD_META = (
	"name",
	"parent",
	"parentfield",
	"parenttype",
	"idx",
	"creation",
	"modified",
	"owner",
	"modified_by",
	"docstatus",
)

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

CARD_ROLES = ("Card Manager", "Card User", "Card Supervisor", "Card Operator")
# v4.0.0: operators use the CARD worker page only, never the Desk (Owner 2026-10-19)
NO_DESK_ROLES = ("Card Operator",)

CMC_DOCTYPE = "Card Monthly Card"
CMC_DEFAULT_PRINT_FORMAT = (
	"Card Monthly Card Print"  # F.8: the professional RTL format (legacy fixture stays as an alternative)
)

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


def ensure_card_roles():
	"""Idempotently create the Card roles. Shared by before_install and the
	v1_2 patch so fresh installs and existing sites end up identical."""
	for role in CARD_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role, "desk_access": 0 if role in NO_DESK_ROLES else 1}
			).insert(ignore_permissions=True)


def before_install():
	"""Run before the app's DocTypes/entities are synced by install-app.

	Adopts any pre-existing legacy CARD config so the standard app files
	sync onto the existing tables/records with no data loss and no
	collision.
	"""
	ensure_card_roles()
	_adopt_module_def()
	_adopt_doctypes()
	_ensure_card_desk_icon()
	# Raw set_value writes above bypass doc hooks; clear caches so the DocType
	# sync that install-app runs next sees the adopted ownership.
	frappe.clear_cache()
	# Install hooks run outside a request transaction; the adopted ownership must
	# be persisted before install-app's DocType sync reads it.
	frappe.db.commit()  # nosemgrep


def after_install():
	"""Run after the app's entities are synced. Reconciles the remaining
	post-sync invariants (print default, disabled legacy scripts, single
	Desk launcher)."""
	_reconcile()
	# Same install-hook context as before_install: persist the reconciliation.
	frappe.db.commit()  # nosemgrep


def before_tests():
	"""Create the shared test masters COMMITTED, once per test run.

	The suite's _ensure_masters() creates missing masters inside the test
	transaction; on a clean CI site a full rollback anywhere in an earlier
	test class erases them for every later class (Supplier inserts then fail
	link validation on "Test Supplier Group"). A seeded site already has all
	of these, so this is a no-op there."""
	from card.dimension import ensure_card_equipment_dimension
	from card.tests.test_controllers import _ensure_masters

	frappe.clear_cache()
	_ensure_masters()
	# S3 posting is fail-closed on the Card Equipment accounting dimension
	# (preflight.require_equipment_dimension), so a clean test site must get it
	# here — the committed bootstrap is the only automated caller (its ALTER
	# TABLEs must never run inside a test transaction).
	ensure_card_equipment_dimension()
	# Test-bootstrap context, outside any test transaction by design.
	frappe.db.commit()  # nosemgrep


def _reconcile():
	"""Idempotent post-install reconciliation. Shared by after_install and
	the v1_0 migration patch so the install hook and the patch can never
	drift apart."""
	_retire_legacy_custom_module()
	_ensure_print_default_property_setter()
	# F.8: fresh installs mark all patches as completed, so the v1_2 print-default
	# patch never runs for them — call the same idempotent logic here (voucher
	# print defaults + CARD Letter Head).
	from card.patches.v1_2.ensure_print_defaults import execute as _ensure_v12_print_defaults

	_ensure_v12_print_defaults()
	disable_legacy_scripts()
	_ensure_card_desk_icon()
	_append_card_to_user_layouts()
	# disable_legacy_scripts() writes Server/Client Script rows via set_value
	# (no doc hooks), so the server_script_map / client-script caches would keep
	# the legacy scripts live alongside the new controllers. Clear so the
	# disabled state takes effect immediately, not only at the next cache clear.
	frappe.clear_cache()


def _adopt_module_def():
	"""Re-point an existing Module Def "Card" to this app WITHOUT deleting it.

	A legacy install owns it as a custom module (``app_name != "card"``);
	hand it to the app so install-app does not raise DuplicateEntryError.
	Never force-deletes a row (safe for a production target).
	"""
	if not frappe.db.exists("Module Def", MODULE):
		return
	current = frappe.db.get_value("Module Def", MODULE, ["app_name", "custom"], as_dict=True)
	# Only adopt a LEGACY custom module (custom=1). Never re-point a Module Def
	# that another installed app already owns as standard (custom=0, app!=card).
	if current.custom:
		frappe.db.set_value(
			"Module Def",
			MODULE,
			{"app_name": APP_NAME, "custom": 0},
			update_modified=False,
		)


def _sidebar_item_key(item):
	"""Identity of a Sidebar Item for de-duplication in the merge path:
	(type, link_type, link_to, label) — as the owner specified."""
	return (item.get("type"), item.get("link_type"), item.get("link_to"), item.get("label"))


def _fold_legacy_sidebar():
	"""Fold the frappe-16.50 ``Sidebar`` the upgrade built for the legacy module into the
	canonical ``Card`` sidebar.

	16.50 added the ``Sidebar`` doctype. ``frappe/patches/v16_0/convert_sidebars.py`` runs
	before this app patch and — while the module was still ``Card (Custom)`` — built a
	``Sidebar`` named and moduled ``Card (Custom)`` from the Card navigation. The desk resolves
	a module's sidebar by ``{"name": module, "module": module}`` then ``{"module": module}``
	(frappe ``sidebar.py`` ``get_module_shell``), so that record must become
	name=``Card`` / module=``Card`` or the Card desk falls back to a generated sidebar.

	Guarded for pre-16.50 sites (no ``Sidebar`` doctype). Idempotent. Never deletes a legacy
	sidebar whose items are not all present in the canonical one.
	"""
	if not frappe.db.exists("DocType", "Sidebar"):
		return
	for name in frappe.get_all("Sidebar", filters={"module": LEGACY_MODULE}, pluck="name"):
		if not frappe.db.exists("Sidebar", MODULE):
			# No canonical sidebar yet -> rename this one. The module-level rename_doc with
			# validate=False runs the rename mechanics (name + child parent + link/dynamic-link
			# updates + after_rename -> dock rows) but SKIPS before_rename/validate_rename and
			# never calls Sidebar.validate (verified in frappe v16.51.1 model/rename_doc.py), so
			# the app-owned/developer-mode guard is bypassed. Then set title+module so the record
			# is title==module ("Card"), which a later normal desk save validates cleanly
			# (validate_title_is_its_own / validate_title_has_its_own_url).
			_rename_doc(
				"Sidebar",
				name,
				MODULE,
				force=True,
				merge=False,
				validate=False,
				show_alert=False,
				rebuild_search=False,
			)
			frappe.db.set_value("Sidebar", MODULE, "module", MODULE, update_modified=False)
			frappe.db.set_value("Sidebar", MODULE, "title", MODULE, update_modified=False)
			continue
		# A canonical "Card" sidebar already exists -> append only the missing items at DB level
		# (no parent .save(), so Sidebar.validate is never invoked).
		dst_keys = {
			_sidebar_item_key(i)
			for i in frappe.get_all(
				"Sidebar Item",
				filters={"parent": MODULE, "parenttype": "Sidebar"},
				fields=["type", "link_type", "link_to", "label"],
			)
		}
		src_items = frappe.get_all(
			"Sidebar Item",
			filters={"parent": name, "parenttype": "Sidebar"},
			fields=["*"],
			order_by="idx asc",
		)
		next_idx = frappe.db.sql(
			"SELECT COALESCE(MAX(idx), 0) FROM `tabSidebar Item` WHERE parent=%s AND parenttype='Sidebar'",
			MODULE,
		)[0][0]
		for it in src_items:
			if _sidebar_item_key(it) in dst_keys:
				continue
			next_idx += 1
			_db_insert_sidebar_item(it, parent=MODULE, idx=next_idx)
			dst_keys.add(_sidebar_item_key(it))
		# delete the legacy ONLY if every one of its items is now present canonically
		if all(_sidebar_item_key(it) in dst_keys for it in src_items):
			frappe.db.delete("Sidebar Item", {"parent": name, "parenttype": "Sidebar"})
			frappe.db.delete("Sidebar", {"name": name})
		else:
			frappe.logger("card").warning(
				"card: kept Sidebar '%s' — not all items present in '%s'" % (name, MODULE)
			)


def _db_insert_sidebar_item(src_row, parent, idx):
	"""Insert one ``Sidebar Item`` child row directly (no parent save → no Sidebar.validate)."""
	child = frappe.new_doc("Sidebar Item")
	for key, value in src_row.items():
		if key not in _SIDEBAR_CHILD_META:
			child.set(key, value)
	child.parent = parent
	child.parenttype = "Sidebar"
	child.parentfield = "items"
	child.idx = idx
	child.name = frappe.generate_hash(length=10)
	child.owner = child.modified_by = frappe.session.user or "Administrator"
	child.creation = child.modified = now()
	child.db_insert()


def _retire_legacy_custom_module():
	"""Retire the legacy ``Card (Custom)`` Module Def left by the original
	in-site customization (the app ships only ``Card`` in modules.txt).

	Idempotent: no-op when the legacy module is already gone. First folds the
	frappe-16.50 ``Sidebar`` into the canonical ``Card`` one (see
	_fold_legacy_sidebar), then reassigns any other doc still scoped to
	``Card (Custom)`` to the canonical ``Card`` module across every
	module-scoped DocType, then deletes the Module Def ONLY if nothing
	references it anymore. If anything still does (or the delete is refused),
	it logs and keeps the row — never force-deletes, so it is safe on a
	production target and never breaks ``bench migrate``.
	"""
	if not frappe.db.exists("Module Def", LEGACY_MODULE):
		return

	# frappe 16.50 `Sidebar` first: the desk resolves a module's sidebar by name==module, so a
	# blind module-reassignment is not enough — the record must be RENAMED to "Card". Handle it
	# authoritatively here (guarded for pre-16.50 sites).
	_fold_legacy_sidebar()

	# Every DocType that scopes records by Module Def (a standard Link field
	# "module" -> "Module Def"), plus DocType itself (direct column).
	scoped = frappe.get_all(
		"DocField",
		filters={"fieldname": "module", "fieldtype": "Link", "options": "Module Def"},
		pluck="parent",
	)
	scoped = sorted(set(scoped) | {"DocType"})

	# `Sidebar` is owned by _fold_legacy_sidebar() above (a rename, which a blind module write
	# cannot do); reassign every OTHER module-scoped doctype to the canonical module.
	for dt in scoped:
		if dt == "Sidebar" or not frappe.db.has_column(dt, "module"):
			continue
		for nm in frappe.get_all(dt, filters={"module": LEGACY_MODULE}, pluck="name"):
			frappe.db.set_value(dt, nm, "module", MODULE, update_modified=False)

	# reference count INCLUDES Sidebar: a legacy sidebar the fold deliberately KEPT (its items
	# are not all present canonically) legitimately blocks retirement of the Module Def.
	remaining = 0
	for dt in scoped:
		if not frappe.db.has_column(dt, "module"):
			continue
		remaining += frappe.db.count(dt, {"module": LEGACY_MODULE})

	if remaining:
		frappe.logger("card").warning(
			"card: kept Module Def '%s' — %d doc(s) still reference it" % (LEGACY_MODULE, remaining)
		)
		return
	try:
		frappe.delete_doc("Module Def", LEGACY_MODULE, ignore_permissions=True)
		frappe.logger("card").info("card: retired legacy Module Def '%s'" % LEGACY_MODULE)
	except Exception:
		# A residual link we did not reassign can make core refuse the delete;
		# keep the empty module rather than fail migrate.
		frappe.logger("card").warning("card: could not delete Module Def '%s' (kept)" % LEGACY_MODULE)


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
		# Only adopt a LEGACY custom DocType (custom=1). A standard DocType of
		# the same name owned by another app is left untouched (never stolen).
		if not current.custom:
			continue
		frappe.db.set_value("DocType", dt, {"custom": 0, "module": MODULE}, update_modified=False)

	if frappe.db.exists("DocType", CMC_DOCTYPE) and frappe.db.get_value(
		"DocType", CMC_DOCTYPE, "default_print_format"
	):
		frappe.db.set_value("DocType", CMC_DOCTYPE, "default_print_format", None, update_modified=False)


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
	"""Guarantee exactly ONE app-owned Desk launcher for Card, with the logo.

	The canonical icon is the STANDARD one shipped as card/desktop_icon/card.json
	(name "Card"); install/migrate sync it and migrate's orphan-prune keeps it
	because it is file-backed. This function's job is to (1) remove any LEGACY
	standard=0 "Card" launcher (production had one, no backing file) so it does
	not shadow or duplicate the app icon, and (2) make sure the standard icon
	exists with the right fields.

	It NEVER force-deletes a standard=1 icon: in developer mode deleting a
	standard Desktop Icon also deletes its export file (card/desktop_icon/
	card.json), after which orphan-prune would drop the icon entirely. Only
	standard=0 rows (which have no backing file) are deleted.
	"""
	rows = frappe.get_all(
		"Desktop Icon",
		filters={"label": DESK_ICON_LABEL},
		fields=["name", "link_to", "app", "standard"],
	)
	# Card-launcher candidates only; an unrelated standard icon merely sharing
	# the label "Card" (another app, different link) is left untouched.
	candidates = [r for r in rows if r.app == APP_NAME or r.link_to == MODULE or not r.standard]

	# 1) Remove legacy standard=0 launchers only (no backing file -> safe).
	for r in candidates:
		if not r.standard:
			frappe.delete_doc("Desktop Icon", r.name, force=1, ignore_permissions=True)

	fields = {
		"standard": 1,
		"app": APP_NAME,
		"icon_type": "Link",
		"link_type": "Workspace Sidebar",
		"link_to": MODULE,
		"logo_url": CARD_LOGO_URL,
		"hidden": 0,
	}
	# 2) Ensure the standard icon. Upsert an existing standard launcher; else
	#    create it as name "Card" so it coincides with the shipped file (no
	#    duplicate after sync). Any extra unbacked standard row is removed by
	#    migrate's orphan-prune, never force-deleted here.
	standard = [r.name for r in candidates if r.standard]
	if standard:
		frappe.db.set_value("Desktop Icon", standard[0], fields, update_modified=False)
	elif not frappe.db.exists("Desktop Icon", MODULE):
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
		[
			"label",
			"icon_type",
			"link_type",
			"link_to",
			"app",
			"icon",
			"logo_url",
			"bg_color",
			"standard",
			"restrict_removal",
		],
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
			frappe.db.set_value(
				"Desktop Layout",
				name,
				"layout",
				json.dumps(items, ensure_ascii=False),
				update_modified=False,
			)
			updated.append(user)

	if updated:
		# Log the count only, not the user ids (avoid PII in logs).
		frappe.logger("card").info("card: reconciled Card launcher in %d Desktop Layout(s)" % len(updated))
	return updated


def disable_legacy_scripts():
	"""Disable (never delete) the legacy Server/Client Scripts.

	Idempotent: only writes rows that are not already disabled. Shared by
	``after_install`` and the ``v1_0`` migration patch.
	"""
	for name in LEGACY_SERVER_SCRIPTS:
		if (
			frappe.db.exists("Server Script", name)
			and frappe.db.get_value("Server Script", name, "disabled") != 1
		):
			frappe.db.set_value("Server Script", name, "disabled", 1, update_modified=False)

	for name in LEGACY_CLIENT_SCRIPTS:
		if (
			frappe.db.exists("Client Script", name)
			and frappe.db.get_value("Client Script", name, "enabled") != 0
		):
			frappe.db.set_value("Client Script", name, "enabled", 0, update_modified=False)
