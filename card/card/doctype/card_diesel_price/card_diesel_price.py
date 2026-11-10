# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe.model.document import Document


class CardDieselPrice(Document):
	"""FR-125: one effective-dated diesel price per litre of a company (Card Settings > Diesel price
	schedule). Validated by CardSettings; read by project_diesel_fill.diesel_price."""
