# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe.model.document import Document

from card.transfer import apply_transfer, check_cancel_allowed, reverse_transfer


class EquipmentTransport(Document):
	# The accounting posting (Purchase Invoice to the transport supplier, cost on the
	# project) is added in a later stage, gated by owner approval.
	def on_submit(self):
		# Transport = a location transfer: move the equipment to the new project.
		apply_transfer(self)

	def before_cancel(self):
		# Guards run before docstatus flips, so a block keeps the doc submitted.
		check_cancel_allowed(self)

	def on_cancel(self):
		reverse_transfer(self)
