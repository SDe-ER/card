# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-160 (#31; closure plan WP-J): one row of an Equipment Operating Group.

A plain child document — every rule (unique equipment per active group, date validity,
cross-company refusal) lives on the parent ``Equipment Operating Group`` controller so it
can take a parent-level locking read before the check (Lesson 4)."""

from frappe.model.document import Document


class EquipmentOperatingGroupMember(Document):
	pass
