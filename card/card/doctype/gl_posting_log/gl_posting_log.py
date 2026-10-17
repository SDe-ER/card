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


# the party field of each posting document the builder creates
POSTING_PARTY = {"Purchase Invoice": ("Supplier", "supplier"), "Sales Invoice": ("Customer", "customer")}


class GLPostingLog(Document):
	"""#57: the audit record of a CARD posting, guarding _block_amended_copy (#55).
	Only card.gl.posting.build_monthly_posting creates one; afterwards it moves
	only through db_set in card.gl.events (which does not run validate). No user,
	role or share may edit or delete it, whatever the DocPerm says."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Posting log {0} is an audit record and cannot be edited.").format(self.name))
		self.validate_builder_insert()
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

	def validate_builder_insert(self):
		"""#57: the builder marks the log it inserts (document flags cannot be
		set from a request: "flags" is a reserved key), and the log must match
		what the builder writes: its own posting document, of the same company
		and party, still a draft for an invoice, and the only log of that document."""
		if not self.flags.get("card_gl_build"):
			frappe.throw(
				_("Posting logs are created only by CARD's monthly posting."), frappe.PermissionError
			)
		party_type, party_field = POSTING_PARTY.get(self.posting_doctype, (None, None))
		fields = ["company", "docstatus", "creation"] + ([party_field] if party_field else [])
		doc = (
			self.posting_doc
			and self.posting_doctype == self.posting_type
			and frappe.db.get_value(self.posting_doctype, self.posting_doc, fields, as_dict=True)
		)
		if (
			not doc
			or not doc.creation
			or doc.company != self.company
			or (party_field and (doc.docstatus != 0 or self.party_type != party_type))
			or (party_field and doc.get(party_field) != self.party)
			or frappe.db.exists(
				"GL Posting Log",
				{
					"posting_doctype": self.posting_doctype,
					"posting_doc": self.posting_doc,
					"creation": [">=", doc.creation],
				},
			)
		):
			frappe.throw(
				_("Posting logs are created only by CARD's monthly posting."), frappe.PermissionError
			)

	def on_trash(self):
		"""#57: never deleted — not active, cancelled or stale logs either: the
		log is the audit record (and _block_amended_copy needs it). Deleting a
		DRAFT posting document flips its log to Cancelled (card.gl.events.on_trash).
		Delete Company Transactions deletes in bulk without on_trash, and app
		uninstall passes ignore_on_trash."""
		frappe.throw(
			_("Posting log {0} is the audit record of a CARD posting and cannot be deleted.").format(
				self.name
			)
		)
