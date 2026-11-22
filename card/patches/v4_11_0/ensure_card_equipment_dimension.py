# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-176 (Owner decision 2026-11-22): the app creates the official ERPNext Accounting Dimension "Card Equipment"
itself, so supplier payments, invoices and journal lines can carry the equipment. Idempotent: a site that already
has the dimension is left as it is; a second migrate changes nothing. Not mandatory for any company.

Writes: one Accounting Dimension (with a non-mandatory default row per company) and ERPNext's standard
`card_equipment` custom field on each accounting doctype (empty columns). Never changes a document, amount,
GL entry or permission."""

from card.dimension import ensure_card_equipment_dimension


def execute():
	ensure_card_equipment_dimension()
