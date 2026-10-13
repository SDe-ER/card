app_name = "card"
app_title = "CARD"
app_publisher = "Ahmed Shehab"
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
# jinja = {
# 	"methods": "card.utils.jinja_methods",
# 	"filters": "card.utils.jinja_filters"
# }

# Installation
# ------------

before_install = "card.install.before_install"
after_install = "card.install.after_install"

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

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

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

# Scheduled Tasks
# ---------------

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

# before_tests = "card.install.before_tests"

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

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

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
	{"dt": "Number Card", "filters": [["module", "=", "Card"]]},
	{"dt": "Dashboard Chart", "filters": [["module", "=", "Card"]]},
	{"dt": "Print Format", "filters": [["module", "=", "Card"]]},
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

add_to_apps_screen = [
	{
		"name": "card",
		"logo": "/assets/card/images/card-logo.svg",
		"title": "Card",
		"route": "/app/card",
	}
]

# NOTE: app_logo_url is intentionally NOT set. On a shared site the last
# installed app's app_logo_url replaces the navbar/login logo for every user;
# a standalone app must not rebrand the host. The Card launcher logo is carried
# by the Desktop Icon (card/desktop_icon/card.json) and add_to_apps_screen.
