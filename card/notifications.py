# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Gated notifications. Each helper is a no-op (baseline) unless its Card
Settings flag is on, so the default-off configuration changes nothing."""

import frappe

from card.settings import setting


def notify(flag, recipients, subject, message, doc=None):
	"""Create a Notification Log for each recipient, only when `flag` is on."""
	if not setting(flag):
		return 0
	sent = 0
	for user in sorted({u for u in (recipients or []) if u and u not in ("Administrator", "Guest")}):
		try:
			frappe.get_doc({
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"email_content": message,
				"document_type": doc.doctype if doc else None,
				"document_name": doc.name if doc else None,
			}).insert(ignore_permissions=True)
			sent += 1
		except Exception:
			frappe.logger("card.notifications").warning("notify failed for %s" % user)
	return sent
