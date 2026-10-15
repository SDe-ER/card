# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE

import frappe
from frappe.model.document import Document

ACTIVE_STATES = ("Draft", "Submitted")


def build_posting_key(company, party_type, party, month, year, posting_type):
	"""Deterministic composite key for the uniqueness guard."""
	return "|".join(
		[
			str(company or ""),
			str(party_type or ""),
			str(party or ""),
			"%02d" % int(month) if str(month).isdigit() else str(month or ""),
			str(int(year)) if str(year).isdigit() else str(year or ""),
			str(posting_type or ""),
		]
	)


class GLPostingLog(Document):
	def validate(self):
		# Active (Draft/Submitted) rows carry the composite key so the DB unique
		# index blocks a second active posting for the same party+period+type.
		# Cancelled/Failed rows clear the key (NULL) so a corrected posting can
		# be re-created (MySQL allows many NULLs in a unique index).
		if self.status in ACTIVE_STATES:
			self.posting_key = build_posting_key(
				self.company, self.party_type, self.party, self.month, self.year, self.posting_type
			)
			# supplementary postings (late sources after the primary was
			# submitted) stay unique per sequence
			if (self.sequence or 1) > 1:
				self.posting_key = "{0}|{1}".format(self.posting_key, self.sequence)
		else:
			self.posting_key = None
