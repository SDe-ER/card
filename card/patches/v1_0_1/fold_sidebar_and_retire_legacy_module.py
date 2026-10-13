# Copyright (c) 2026, Ahmed Shehab and contributors
# For license information, please see license.txt
"""v1.0.1: fold the frappe-16.50 `Sidebar` + retire the legacy ``Card (Custom)`` Module Def.

A NEW patch entry on purpose. The reconciliation lives in ``card.install._reconcile`` and was
previously reached on an upgrade only through ``card.patches.v1_0.reconcile_card_config`` — but
that patch is already in the Patch Log of every v1.0 site, so frappe skips it, and ``hooks.py``
has no ``after_migrate`` hook. So on an already-installed site the fold/retire would never run.
This fresh entry runs once (it is not yet in any Patch Log) and is itself idempotent.
"""

import frappe

from card import install


def execute():
	# _retire_legacy_custom_module() folds the 16.50 Sidebar into the canonical "Card" one first,
	# then reassigns any other module-scoped doc and retires the Module Def when unreferenced.
	install._retire_legacy_custom_module()
	frappe.clear_cache()
