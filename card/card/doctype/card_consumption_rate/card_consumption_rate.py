# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe.model.document import Document


class CardConsumptionRate(Document):
	"""FR-144: one effective-dated diesel consumption rate in litres per operating hour, on a Card
	Equipment Type (the type default) or on a Card Equipment (its override). Equipment data, not an
	amount. Validated by its parent (card.consumption.validate_consumption_rates); read by
	card.consumption.consumption_rate. Permission is the parent's (Frappe child-table rules)."""
