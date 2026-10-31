# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Shared CARD constants (import-free so any module can use them)."""

OWNED = "ملك"
THIRD_PARTY = "طرف ثالث"  # managed for another owner; may link an Asset, never a rented machine

# rental direction (phase F.7: lives on Card Equipment, mirrored read-only on cards)
DIR_RENTED_IN = "مستأجَرة من مورد"  # we rent it from a supplier (supplier PI side)
DIR_RENTED_OUT = "مؤجَّرة لعميل"  # we rent owned equipment to a customer (customer SI side)
DIR_SUBRENTAL = "إيجار من الباطن"  # rented from a supplier AND rented out to a customer
DIR_INTERNAL = "تشغيل داخلي"  # owned, used internally, no billing
CUSTOMER_BILLING_DIRECTIONS = (DIR_RENTED_OUT, DIR_SUBRENTAL)
SUPPLIER_BILLING_DIRECTIONS = (DIR_RENTED_IN, DIR_SUBRENTAL)


def allowed_directions(ownership):
	"""Directions an equipment's ownership permits. ملك runs internally or is
	rented out; anything else (إيجار and the existing طرف ثالث, whose managed
	flow is deferred) is the rented side."""
	if ownership == OWNED:
		return (DIR_RENTED_OUT, DIR_INTERNAL)
	return (DIR_RENTED_IN, DIR_SUBRENTAL)


def derive_direction(ownership):
	"""Default direction for equipment that never chose one (legacy rows,
	backfill patch, and the server-side blank-value fallback)."""
	return DIR_INTERNAL if ownership == OWNED else DIR_RENTED_IN
