# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE

from frappe.model.document import Document


class CardAdjustmentType(Document):
	# Row-level rules live in CardSettings.validate so every save path
	# (including bulk settings edits) revalidates the whole table at once.
	pass
