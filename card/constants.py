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

# card shifts (stored Select values of Card Monthly Card.shift)
SHIFT_DAY = "نهاري"
SHIFT_NIGHT = "ليلي"

# #43/#121/#122 (WP-15): which project gets the move day of a project -> project transport.
# Stored Select values of Card Company Settings.move_day_rule and Equipment Transport.move_day_rule.
# An empty value is the rule CARD always applied (the next day), so nothing changes on deploy.
MOVE_DAY_NEXT = "New assignment starts the day after the move"
MOVE_DAY_SAME = "New assignment starts on the move day"

# FR-122 (#42, #120): Card Equipment.status that stops new use, and the per-company rule
# (Card Company Settings.equipment_status_rule). Empty = Warn, so nothing is refused on deploy.
EQUIPMENT_STATUS_ENDED = "منتهية"
STATUS_RULE_WARN = "Warn"
STATUS_RULE_ENFORCE = "Enforce"


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
