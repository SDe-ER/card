# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe.model.document import Document


class CardTypeConsumptionRate(Document):
	"""FR-144: one effective-dated default consumption rate in litres per operating hour of a Card Equipment Type,
	for one company (`company`) or for every company (empty). Level-0 fields: the type has no level-1 DocPerms;
	writes are limited by CardEquipmentType.validate (card.consumption.validate_type_rate_changes). Read by
	card.consumption.consumption_rate."""
