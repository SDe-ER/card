# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Jinja helpers for the CARD print formats (registered in hooks.jinja)."""

import frappe
from frappe import _
from frappe.utils import flt, money_in_words


def card_amount_in_words(amount, company=None):
	"""The amount in words, in the company's currency.

	Core ``money_in_words`` prefixes the ISO code, translated only with context
	"Currency" — SAR has no Arabic entry, so an Arabic print read "SAR ألفا فقط".
	In Arabic the currency's symbol (the one the printed amount already shows)
	replaces the code; other languages keep the core wording."""
	currency = (
		frappe.get_cached_value("Company", company, "default_currency") if company else None
	) or frappe.db.get_default("currency")
	words = money_in_words(flt(amount), currency)
	if not words or not currency or not (frappe.local.lang or "").startswith("ar"):
		return words
	if _(currency, context="Currency") != currency:
		return words  # the code has a real translation: keep it
	symbol = frappe.get_cached_value("Currency", currency, "symbol")
	if symbol:
		words = words.replace(currency + " ", symbol + " ", 1)
	return words
