app_name = "card"
app_title = "CARD"
app_publisher = "SDCE"
app_description = "Monthly equipment operation cards (standalone CARD app)"
app_email = "info@sdce.sa"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "card",
# 		"logo": "/assets/card/logo.png",
# 		"title": "Card",
# 		"route": "/card",
# 		"has_permission": "card.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/card/css/card.css"
# app_include_js = "/assets/card/js/card.js"

# include js, css files in header of web template
# web_include_css = "/assets/card/css/card.css"
# web_include_js = "/assets/card/js/card.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "card/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "card/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {"methods": ["card.print_utils.card_amount_in_words"]}

# Installation
# ------------

before_install = "card.install.before_install"
after_install = "card.install.after_install"
# F.8: the bundled print fonts install themselves on every migrate (user fontconfig)
# v4.1.2: launcher entries shipped after a site or user saved its own dock layer reach that layer
after_migrate = ["card.fonts.ensure_fonts", "card.navigation.restore_launcher_entries"]

# Uninstallation
# ------------

# before_uninstall = "card.uninstall.before_uninstall"
# after_uninstall = "card.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "card.utils.before_app_install"
# after_app_install = "card.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "card.utils.before_app_uninstall"
# after_app_uninstall = "card.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "card.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "card.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["card.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# The CARD party registries are per party across companies: a user restricted
# to some companies sees only the parties that have cards there (#23).
permission_query_conditions = {
	"Card Equipment Supplier": "card.party_registry.supplier_query_conditions",
	"Card Equipment Customer": "card.party_registry.customer_query_conditions",
	# v4.0.0: an operator sees only his own equipment needs
	"Equipment Needs Request": "card.materials.needs_request_query",
	# P0 2026-10-20: an assignment belongs to its equipment's company
	"Card Equipment Assignment": "card.card.doctype.card_equipment_assignment.card_equipment_assignment.assignment_query_conditions",
	# FR-077: a machine fitment row belongs to its equipment's company
	"Card Equipment Part": "card.card.doctype.card_equipment_part.card_equipment_part.fitment_query_conditions",
	# FR-099/FR-100: meter readings, maintenance orders and machine plans belong to the equipment's company
	"Card Meter Reading": "card.equipment_scope.reading_query_conditions",
	"Card Maintenance Order": "card.equipment_scope.order_query_conditions",
	"Card Maintenance Plan": "card.equipment_scope.plan_query_conditions",
	# R1: a personnel assignment belongs to its employee's company
	"Card Personnel Assignment": "card.equipment_scope.personnel_query_conditions",
}

has_permission = {
	"Card Equipment Supplier": "card.party_registry.has_registry_permission",
	"Card Equipment Customer": "card.party_registry.has_registry_permission",
	"Equipment Needs Request": "card.materials.needs_request_permission",
	"Card Equipment Assignment": "card.card.doctype.card_equipment_assignment.card_equipment_assignment.has_assignment_permission",
	"Card Monthly Card": "card.card.doctype.card_monthly_card.card_monthly_card.has_card_permission",
	"Equipment Transport": "card.card.doctype.equipment_transport.equipment_transport.has_transport_permission",
	"Card Equipment Part": "card.card.doctype.card_equipment_part.card_equipment_part.has_fitment_permission",
	# #113: a cancelled movement with a signed receipt (and so its receipt) is never deleted
	"Employee Tool Custody": "card.card.doctype.employee_tool_custody.employee_tool_custody.has_custody_permission",
	"Card Meter Reading": "card.equipment_scope.has_reading_permission",
	"Card Maintenance Order": "card.equipment_scope.has_order_permission",
	"Card Maintenance Plan": "card.equipment_scope.has_plan_permission",
	"Card Personnel Assignment": "card.equipment_scope.has_personnel_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Period lock (card.period_lock) on the three CARD transactions — validate covers
# save/submit/amend/import; on_cancel + on_trash cover cancel + delete.
_PERIOD_LOCK_EVENTS = {
	"validate": "card.period_lock.on_validate",
	"on_cancel": "card.period_lock.on_cancel",
	"on_trash": "card.period_lock.on_trash",
}
# S3 (4a): a source held by a draft/submitted posting cannot be cancelled
# (and therefore cannot be amended) until the posting is cancelled/deleted.
_SOURCE_EVENTS = dict(_PERIOD_LOCK_EVENTS)
_SOURCE_EVENTS["before_cancel"] = "card.gl.events.block_source_cancel"

# S3 (4b): CARD-created Purchase/Sales Invoices reserve/post/free their source
# documents. The handlers no-op for every invoice without a GL Posting Log row.
_POSTING_EVENTS = {
	"validate": "card.gl.events.validate",
	"before_submit": "card.gl.events.before_submit",
	"on_submit": "card.gl.events.on_submit",
	"before_cancel": "card.gl.events.before_cancel",
	"on_trash": "card.gl.events.on_trash",
}
doc_events = {
	"Card Monthly Card": dict(_SOURCE_EVENTS),
	"Project Diesel Fill": dict(_SOURCE_EVENTS),
	"Equipment Transport": dict(_SOURCE_EVENTS),
	"Purchase Invoice": dict(_POSTING_EVENTS),
	"Sales Invoice": dict(_POSTING_EVENTS),
	# the CARD party registries follow ERPNext renames and merges
	"Supplier": {
		"before_rename": "card.party_registry.before_rename",
		"after_rename": "card.party_registry.after_rename",
	},
	"Customer": {
		"before_rename": "card.party_registry.before_rename",
		"after_rename": "card.party_registry.after_rename",
	},
	# the registries' change history stays hidden from their form (#23)
	"Property Setter": {"before_validate": "card.party_registry.guard_registry_track_changes"},
	# Card Equipment financial privacy: the change history never carries restricted values (2026-10-31)
	"Version": {"before_insert": "card.field_privacy.mask_restricted_version"},
	# FR-098: the ERPNext Asset owns the master data of its linked Card Equipment
	"Asset": {
		"on_update": "card.asset_master.on_asset_change",
		"on_update_after_submit": "card.asset_master.on_asset_change",
		"on_cancel": "card.asset_master.on_asset_change",
	},
	# #113: a signed tool-custody receipt stays a private file of its own custody record
	"File": {
		"before_validate": "card.custody_receipt.keep_private",
		"before_insert": "card.custody_receipt.keep_on_its_record",
		"on_trash": "card.custody_receipt.keep_while_recorded",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	# #56: no-op unless Card Settings enables the daily location sync
	"daily": [
		"card.transfer.sync_equipment_locations_daily",
		# FR-100: maintenance status and service-due alerts
		"card.maintenance.daily_maintenance_scan",
		"card.maintenance.daily_warranty_scan",
		# R1: the equipment operator follows the personnel assignments that start or end
		"card.personnel.daily_operator_sync",
	],
}

# scheduler_events = {
# 	"all": [
# 		"card.tasks.all"
# 	],
# 	"daily": [
# 		"card.tasks.daily"
# 	],
# 	"hourly": [
# 		"card.tasks.hourly"
# 	],
# 	"weekly": [
# 		"card.tasks.weekly"
# 	],
# 	"monthly": [
# 		"card.tasks.monthly"
# 	],
# }

# Testing
# -------

# Committed-once shared test masters (clean CI sites; no-op on seeded sites).
before_tests = "card.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "card.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "card.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "card.task.get_dashboard_data"
# }
override_doctype_dashboards = {
	"Supplier": "card.dashboards.supplier_dashboard",
	"Asset": "card.dashboards.asset_dashboard",
	"Project": "card.dashboards.project_dashboard",
	"Customer": "card.dashboards.customer_dashboard",
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# S3: the GL Posting Log's posting_doc link must never block deleting a DRAFT
# posting (the log row itself flips to Cancelled in card.gl.events.on_trash).
ignore_links_on_delete = ["GL Posting Log"]

# Request Events
# ----------------
# before_request = ["card.utils.before_request"]
# after_request = ["card.utils.after_request"]

# Job Events
# ----------
# before_job = ["card.utils.before_job"]
# after_job = ["card.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"card.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# Fixtures (UI config shipped with the app; exact records exported from card-dev).
# NOTE: Property Setter "Card Monthly Card-main-default_print_format" is intentionally
# EXCLUDED here — it is created idempotently by card.install.after_install.
fixtures = [
	{"dt": "Workspace", "filters": [["name", "=", "Card"]]},
	{"dt": "Workspace Sidebar", "filters": [["name", "=", "Card"]]},
	{"dt": "Sidebar", "filters": [["name", "=", "Card"]]},
	{"dt": "Number Card", "filters": [["module", "=", "Card"]]},
	{"dt": "Dashboard Chart", "filters": [["module", "=", "Card"]]},
	{"dt": "Print Format", "filters": [["module", "=", "Card"], ["standard", "=", "No"]]},
	{"dt": "Role", "filters": [["name", "in", ["Card Manager", "Card User"]]]},
	{
		"dt": "Property Setter",
		"filters": [
			[
				"name",
				"in",
				[
					"Card Monthly Card-operator_name-in_list_view",
					"Card Monthly Card-month-in_list_view",
					"Card Monthly Card-shift-in_list_view",
					"Card Monthly Card-equipment-in_list_view",
					"Card Monthly Card-equipment_name-in_list_view",
				],
			]
		],
	},
]

# The Desk entry stays first: Frappe's boot reads the first entry for the app's dock.
add_to_apps_screen = [
	{
		"name": "card",
		"logo": "/assets/card/images/card-logo.svg",
		"title": "CARD",
		"route": "/app/card",
		"has_permission": "card.mobile.has_desk_app_permission",
	},
	{
		"name": "card",
		"logo": "/assets/card/frontend/icons/icon-192.png",
		"title": "CARD Mobile",
		"route": "/cdms",
		"has_permission": "card.mobile.has_app_permission",
	},
]

# CARD Mobile (frontend/, built into card/public/frontend and card/www/cdms.html), as Frappe HR's
# /hrms. The service worker is served at /cdms/sw.js so that it controls /cdms (card/pwa.py).
website_route_rules = [
	{"from_route": "/cdms/sw.js", "to_route": "cdms-sw"},
	{"from_route": "/cdms/<path:app_path>", "to_route": "cdms"},
]
page_renderer = ["card.pwa.ServiceWorkerRenderer"]

# NOTE: app_logo_url is intentionally NOT set. On a shared site the last
# installed app's app_logo_url replaces the navbar/login logo for every user;
# a standalone app must not rebrand the host. The Card launcher logo is carried
# by the Desktop Icon (card/desktop_icon/card.json) and add_to_apps_screen.
