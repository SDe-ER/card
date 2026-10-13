# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""v1.0.1: fold the frappe-16.50 `Sidebar` + retire the legacy ``Card (Custom)`` Module Def.

A NEW patch entry on purpose. The reconciliation lives in ``card.install._reconcile`` and was
previously reached on an upgrade only through ``card.patches.v1_0.reconcile_card_config`` — but
that patch is already in the Patch Log of every v1.0 site, so frappe skips it, and ``hooks.py``
has no ``after_migrate`` hook. So on an already-installed site the fold/retire would never run.
This fresh entry runs once (it is not yet in any Patch Log) and is itself idempotent.

Resilience: the Sidebar fold is cosmetic (desk navigation) and must NEVER abort ``bench
migrate``. The work runs inside a DB savepoint; any failure is rolled back to the savepoint and
logged, and the patch returns normally. The Workspace ``module`` fix (shipped in the corrected
``workspace.json`` fixture, applied by ``sync_fixtures``) and the ``net_amount`` backfill (its
own patch ``card.patches.v1_0.backfill_net_amount``) are independent of this patch and are not
affected if the fold fails here.
"""

import frappe

from card import install

_SAVEPOINT = "card_v1_0_1_fold"


def execute():
	frappe.db.savepoint(_SAVEPOINT)
	try:
		# folds the 16.50 Sidebar into the canonical "Card" one, then reassigns any other
		# module-scoped doc and retires the Module Def when unreferenced
		install._retire_legacy_custom_module()
	except Exception:
		frappe.db.rollback(save_point=_SAVEPOINT)
		frappe.log_error(
			title="CARD v1.0.1 sidebar fold",
			message=frappe.get_traceback(),
		)
		return
	frappe.clear_cache()
