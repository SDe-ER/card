# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Two-connection concurrency check for the cash-payment executor (FR-170 security finding 2, requirement 4).

Not part of the unit suite: two real database connections must see committed data, and committing test data into a
shared test site would leave grants and records behind for other suites. Run it only on a disposable site.

Procedure (disposable site, never Production):

1. Create an approved and queued cash payment (Card Manager has queued it) and commit it.
2. Run:  bench --site <disposable-site> execute card.tests.concurrency_posting.run --kwargs "{'payment': 'CCD-00001', 'identity': '<service user>'}"

Each worker opens its own connection (frappe.init + frappe.connect), runs the executor as the service identity, and
commits. The payment's row lock (SELECT ... FOR UPDATE) serialises them; the second worker sees the payment Posted and
returns the same entry. The check passes only when both workers succeed and exactly one submitted Journal Entry is
linked to the payment.
"""

import threading

import frappe


def _worker(site, sites_path, payment, identity, outcome, index):
	worker = frappe
	worker.init(site=site, sites_path=sites_path)
	worker.connect()
	try:
		worker.set_user(identity)
		from card.cash_disbursement import execute_posting

		entry = execute_posting(payment)
		worker.db.commit()
		outcome[index] = ("ok", entry)
	except Exception as error:  # the outcome is recorded; the caller decides
		worker.db.rollback()
		outcome[index] = ("error", type(error).__name__ + ": " + str(error)[:300])
	finally:
		worker.destroy()


def run(payment, identity, workers=2):
	"""Run ``workers`` executor calls for one approved payment on separate connections and report the outcome."""
	site = frappe.local.site
	sites_path = frappe.local.sites_path
	outcome = [None] * workers
	threads = [
		threading.Thread(target=_worker, args=(site, sites_path, payment, identity, outcome, index))
		for index in range(workers)
	]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join(timeout=300)
	frappe.db.rollback()
	entry_names = {o[1] for o in outcome if o and o[0] == "ok"}
	submitted = frappe.db.count(
		"Journal Entry",
		{"name": ["in", list(entry_names) or [""]], "docstatus": 1},
	)
	linked = frappe.db.get_value("Card Cash Disbursement", payment, "journal_entry")
	result = {
		"outcome": outcome,
		"distinct_entries": sorted(entry_names),
		"submitted_entries": submitted,
		"linked_entry": linked,
		"passed": all(o and o[0] == "ok" for o in outcome)
		and len(entry_names) == 1
		and submitted == 1
		and linked in entry_names,
	}
	print(result)
	return result
