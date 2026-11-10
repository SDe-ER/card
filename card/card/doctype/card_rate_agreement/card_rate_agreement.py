# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-141 (#41): a dated rate agreement. The rules live in card.agreements; nothing reads an agreement yet."""

from frappe.model.document import Document

from card.agreements import validate_agreement


class CardRateAgreement(Document):
	def validate(self):
		validate_agreement(self)
