# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-142: per-company rules of the Card Daily Log. One record per company; a company without a record uses the
defaults (self-approval rule "Warn"). Read by the server in card.daily_log.self_approval_rule."""

from frappe.model.document import Document


class CardDailyLogSettings(Document):
	pass
