app_name = "doftwerks_nrs"
app_title = "NRS E-Invoicing"
app_publisher = "YoungAndCode LTD"
app_description = "NRS e-invoicing for ERPNext"
app_email = "info@youngandcodeltd.com"
app_license = "mit"

# Fixtures
# --------
# Custom Fields added by this app on core/ERPNext doctypes. Only fields on the
# doctypes we extend and with the nrs_ prefix are exported.
fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			["dt", "in", ["Customer", "Item", "Sales Invoice"]],
			["fieldname", "like", "nrs_%"],
		],
	},
	{
		"dt": "Print Format",
		"filters": [["module", "=", "NRS E-Invoicing"]],
	},
	{
		"dt": "E-Invoice Provider",
		"filters": [["name", "=", "doftwerks"]],
	},
]

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "doftwerks_nrs",
# 		"logo": "/assets/doftwerks_nrs/logo.png",
# 		"title": "Doftwerks NRS E-Invoicing",
# 		"route": "/doftwerks_nrs",
# 		"has_permission": "doftwerks_nrs.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/doftwerks_nrs/css/doftwerks_nrs.css"
# app_include_js = "/assets/doftwerks_nrs/js/doftwerks_nrs.js"

# include js, css files in header of web template
# web_include_css = "/assets/doftwerks_nrs/css/doftwerks_nrs.css"
# web_include_js = "/assets/doftwerks_nrs/js/doftwerks_nrs.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "doftwerks_nrs/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
	"Item": "public/js/item.js",
	"Customer": "public/js/customer.js",
}
doctype_list_js = {"Sales Invoice": "public/js/sales_invoice_list.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "doftwerks_nrs/public/icons.svg"

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

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "doftwerks_nrs.utils.jinja_methods",
# 	"filters": "doftwerks_nrs.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "doftwerks_nrs.install.before_install"
# after_install = "doftwerks_nrs.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "doftwerks_nrs.uninstall.before_uninstall"
# after_uninstall = "doftwerks_nrs.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "doftwerks_nrs.utils.before_app_install"
# after_app_install = "doftwerks_nrs.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "doftwerks_nrs.utils.before_app_uninstall"
# after_app_uninstall = "doftwerks_nrs.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "doftwerks_nrs.notifications.get_notification_config"

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

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
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

doc_events = {
	"Sales Invoice": {
		"validate": "doftwerks_nrs.einvoice.set_receipt_type",
		"on_submit": "doftwerks_nrs.einvoice.transmit_on_submit",
		"before_cancel": "doftwerks_nrs.einvoice.block_cancel_after_transmit",
	},
	"Payment Entry": {
		"on_submit": "doftwerks_nrs.einvoice.push_payment_status_on_submit",
		"on_cancel": "doftwerks_nrs.einvoice.push_payment_status_on_submit",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"doftwerks_nrs.tasks.all"
# 	],
# 	"daily": [
# 		"doftwerks_nrs.tasks.daily"
# 	],
# 	"hourly": [
# 		"doftwerks_nrs.tasks.hourly"
# 	],
# 	"weekly": [
# 		"doftwerks_nrs.tasks.weekly"
# 	],
# 	"monthly": [
# 		"doftwerks_nrs.tasks.monthly"
# 	],
# }

# Testing
# -------

# bootstrap a bare CI site (test company, item groups, UOMs) before tests;
# guarded internally, so it is a no-op on an already-set-up site
before_tests = "doftwerks_nrs.tests.utils.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "doftwerks_nrs.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "doftwerks_nrs.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["doftwerks_nrs.utils.before_request"]
# after_request = ["doftwerks_nrs.utils.after_request"]

# Job Events
# ----------
# before_job = ["doftwerks_nrs.utils.before_job"]
# after_job = ["doftwerks_nrs.utils.after_job"]

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
# 	"doftwerks_nrs.auth.validate"
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

# NRS reconciliation: webhooks are the primary status sync; this daily sweep
# is the safety net for missed deliveries and offline-failure retries.
scheduler_events = {
	"daily": [
		"doftwerks_nrs.einvoice.reconcile_transmissions",
	],
}

add_to_apps_screen = [
	{
		"name": "doftwerks_nrs",
		"logo": "/assets/doftwerks_nrs/images/nrs-einvoice-logo.png",
		"title": "NRS E-Invoicing",
		"route": "/app/nrs-e-invoice-settings",
	}
]
