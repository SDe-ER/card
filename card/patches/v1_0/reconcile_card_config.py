# Copyright (c) 2026, Ahmed Shehab and contributors
# For license information, please see license.txt
"""Idempotently reconcile the CARD app's post-install invariants.

Runs on every ``bench migrate``. Complements ``card.install.after_install``
for sites installed before this patch existed, or upgraded in place:
- the Card Monthly Card default print format Property Setter,
- the disabled legacy Server/Client Scripts,
- exactly one app-owned "Card" Desk launcher with the official logo.

Delegates to the single shared implementation so the install hook and the
patch can never drift apart.
"""

from card.install import _reconcile


def execute():
	_reconcile()
