# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Catalog phase 2a (FR-077): equipment make / model masters and part fitment rows.
A fitment row says that an ERPNext Item fits an equipment model or one machine. Its
status follows the DESIGN v4.1 states, and only a second, independent reviewer can
make it final (Owner decision Q5, 2026-10-23)."""

import re

import frappe

APPROVER_ROLES = ("Card Manager", "System Manager")

PENDING = "Pending Technical Review"
CONFIRMED = "Confirmed"
NOT_COMPATIBLE = "Not Compatible"
DECISIONS = (CONFIRMED, NOT_COMPATIBLE)
SECOND_REVIEW = "Pending Second Review"

APPLIES_TO_MODEL = "Equipment Model"
APPLIES_TO_MACHINE = "Equipment"

_SEPARATORS = re.compile(r"[\s\-_./]+")


def normalise(value):
	"""Upper case without spaces, dashes, dots, underscores or slashes, so that
	"PC200-8" and "pc 200 8" give the same key."""
	return _SEPARATORS.sub("", value or "").upper()


def is_approver(user=None):
	return bool(set(APPROVER_ROLES) & set(frappe.get_roles(user or frappe.session.user)))
