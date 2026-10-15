# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe.model.document import Document


class CardEquipmentCustomer(Document):
	# Registry/directory record only: operational counters recomputed from the
	# cards (card.api.recompute_customer). Money balances are never stored here —
	# they live in the official AR (Sales Invoice / Payment Entry / GL Entry).
	pass
