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

# third-party-owned equipment (Card Equipment.owner_model, stored Select values; Owner 2026-11-10).
# The owner's entitlement is informational only (Crusher Owner Statement); CARD never posts it.
OWNER_MODEL_MANAGED = "Managed partner"  # SDCE operates the machine for its owner
OWNER_MODEL_SELF = "Self-operating owner"  # the owner operates it under the company's name
OWNER_MODELS = (OWNER_MODEL_MANAGED, OWNER_MODEL_SELF)

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
STATUS_RULE_WARN = "Warn only (equipment status)"
STATUS_RULE_ENFORCE = "Refuse (equipment status)"

# #43/#48/#121 (WP-14): payers of a transport the company does not pay. Their agreed amount
# (Equipment Transport.informational_amount) is information only: never company cost, never posted.
OTHER_PARTY = "Other Party"
NON_COMPANY_PAYERS = ("Equipment Supplier", "Customer", OTHER_PARTY)
# who may be named as the other party that bears a move (Equipment Transport.party_type)
OTHER_PARTY_TYPES = ("Supplier", "Customer", "Employee")


def allowed_directions(ownership):
	"""Directions an equipment's ownership permits. ملك runs internally or is
	rented out; طرف ثالث (another owner's machine) is also rented out to a customer
	on the company's name (Owner 2026-11-10), besides the rented side; anything
	else (إيجار) is the rented side."""
	if ownership == OWNED:
		return (DIR_RENTED_OUT, DIR_INTERNAL)
	if ownership == THIRD_PARTY:
		return (DIR_RENTED_OUT, DIR_RENTED_IN, DIR_SUBRENTAL)
	return (DIR_RENTED_IN, DIR_SUBRENTAL)


def derive_direction(ownership):
	"""Default direction for equipment that never chose one (legacy rows,
	backfill patch, and the server-side blank-value fallback)."""
	return DIR_INTERNAL if ownership == OWNED else DIR_RENTED_IN
