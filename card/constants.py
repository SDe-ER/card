# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Shared CARD constants (import-free so any module can use them)."""

OWNED = "ملك"

# card direction (customer side, phase E) — stored Arabic values
DIR_RENTED_IN = "مستأجَرة من مورد"  # we rent it from a supplier (supplier PI side)
DIR_RENTED_OUT = "مؤجَّرة لعميل"  # we rent owned equipment to a customer (customer SI side)
DIR_SUBRENTAL = "إيجار من الباطن"  # rented from a supplier AND rented out to a customer
DIR_INTERNAL = "تشغيل داخلي"  # owned, used internally, no billing
CUSTOMER_BILLING_DIRECTIONS = (DIR_RENTED_OUT, DIR_SUBRENTAL)
