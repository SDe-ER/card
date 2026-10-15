# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

ACTIVE_STATES = ("Draft", "Submitted")


def build_posting_key(company, party_type, party, month, year):
	"""Deterministic composite key for the uniqueness guard. G0 §5a: the key is
	TYPE-FREE — one active posting unit per party-month-SIDE, whatever document
	type carries it (a JE and a PI must never both recognize the same month)."""
	return "|".join(
		[
			str(company or ""),
			str(party_type or ""),
			str(party or ""),
			"%02d" % int(month) if str(month).isdigit() else str(month or ""),
			str(int(year)) if str(year).isdigit() else str(year or ""),
		]
	)


class GLPostingLog(Document):
	def validate(self):
		# Active (Draft/Submitted) rows carry the composite key so the DB unique
		# index blocks a second active posting for the same party+period+side.
		# Cancelled/Failed rows clear the key (NULL) so a corrected posting can
		# be re-created (MySQL allows many NULLs in a unique index).
		if self.status in ACTIVE_STATES:
			self.posting_key = build_posting_key(
				self.company, self.party_type, self.party, self.month, self.year
			)
			# supplementary postings (late sources after the primary was
			# submitted) stay unique per sequence
			if (self.sequence or 1) > 1:
				self.posting_key = "{0}|{1}".format(self.posting_key, self.sequence)
		else:
			self.posting_key = None

	def on_trash(self):
		"""H2: the log is the authoritative reservation/audit record — it can
		never be deleted while it is active or while its posting document still
		exists un-cancelled. (Deleting a DRAFT posting document flips the log
		to Cancelled through card.gl.events.on_trash; that is the only path.)"""
		if self.status in ACTIVE_STATES:
			frappe.throw(
				_(
					"Posting log {0} is {1}; cancel or delete its posting documents first — the log itself is the audit record."
				).format(self.name, _(self.status))
			)
		if (
			self.posting_doc
			and self.posting_doctype
			and frappe.db.exists(self.posting_doctype, self.posting_doc)
			and frappe.db.get_value(self.posting_doctype, self.posting_doc, "docstatus") < 2
		):
			frappe.throw(
				_("Posting log {0} still references {1} {2}; it cannot be deleted.").format(
					self.name, _(self.posting_doctype), self.posting_doc
				)
			)
