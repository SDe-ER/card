# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Two-connection concurrency checks for the cash-payment locking paths (FR-170 review, locking order).

Not part of the unit suite: each worker opens its own database connection and must see committed data, so the records
are committed on a disposable test site. Never run it on Production or on a shared site.

Scenarios (each on its own committed synthetic records):

- approval: two Card Managers approve the same pending payment;
- queue: two Card Managers queue the same approved payment;
- posting: two executions of the same queued payment by the accounting service identity;
- cancellation versus posting: the service posts while a Card Manager requests a cancellation;
- duplicate requests: two requests for the same card row.

Each check records every worker outcome and then reads the final state from a fresh transaction. A scenario passes when
the final state is consistent (one linked, submitted entry at most; the status agrees with the entry) and the workers'
outcomes are the ones the lock order allows.

Run on the disposable site:

    bench --site <disposable-site> execute card.tests.concurrency_cash_locking.seed
    bench --site <disposable-site> execute card.tests.concurrency_cash_locking.run_all
"""

import json
import os
import threading

import frappe
from frappe.utils import flt, nowdate

COMPANY = "Test Equipment Co"
USERS = {
	"requester": "fr170.carduser@example.invalid",
	"manager_a": "fr170.manager.a@example.invalid",
	"manager_b": "fr170.manager.b@example.invalid",
	"service": "fr170.posting@example.invalid",
}
STATE_FILE = os.path.expanduser("~/fr170/run/concurrency-state.json")


def _state_path():
	return os.environ.get("FR170_CONCURRENCY_STATE", STATE_FILE)


def _worker(site, sites_path, user, fn, args, outcome, index):
	try:
		frappe.init(site=site, sites_path=sites_path)
		frappe.connect()
		frappe.set_user(user)
		result = fn(*args)
		frappe.db.commit()
		outcome[index] = ("ok", str(result))
	except Exception as error:
		frappe.db.rollback()
		outcome[index] = ("error", type(error).__name__, str(error)[:200])
	finally:
		frappe.destroy()


def _race(jobs):
	"""Run each (user, function, args) on its own connection at the same time; return the outcomes in job order."""
	site, sites_path = frappe.local.site, frappe.local.sites_path
	outcome = [None] * len(jobs)
	threads = [
		threading.Thread(target=_worker, args=(site, sites_path, user, fn, args, outcome, index))
		for index, (user, fn, args) in enumerate(jobs)
	]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join(timeout=300)
	frappe.db.rollback()  # the main connection starts a new transaction before it reads the final state
	return outcome


def _ok(outcome):
	return [o for o in outcome if o and o[0] == "ok"]


def _submitted_entries_for(payment):
	return frappe.get_all(
		"Journal Entry",
		filters={"user_remark": ["like", f"%{payment}%"], "docstatus": 1},
		pluck="name",
	)


def _status(payment):
	return frappe.db.get_value("Card Cash Disbursement", payment, ["status", "journal_entry"], as_dict=True)


def _check_entry_consistency(payment):
	"""A payment that is Posted or Cancellation Requested has exactly one submitted entry linked to it."""
	row = _status(payment)
	entries = _submitted_entries_for(payment)
	ok = len(entries) <= 1
	if row.status in ("Posted", "Cancellation Requested"):
		ok = ok and entries == [row.journal_entry] and row.journal_entry is not None
	return {"status": row.status, "linked": row.journal_entry, "submitted_entries": entries, "consistent": ok}


# ---------- seed (committed synthetic records on the disposable site) ----------


def seed():
	"""Create the synthetic cards and payments the scenarios need. Each scenario has its own card row."""
	from card.cash_disbursement import (
		approve_cash_disbursement,
		queue_posting,
		request_cash_disbursement,
	)
	from card.tests.test_cash_disbursement_db import _cash_account
	from card.tests.test_s3_posting import _PostingBase

	_PostingBase.setUpClass()
	base = _PostingBase("run")
	base.setUp()
	cash = _cash_account(base.company)
	names = {}
	for scenario in ("approval", "queue", "posting", "cancel_vs_posting", "duplicate"):
		eq = base._equipment()
		card = base._card(
			eq,
			[5],
			adjustments=[
				{
					"adjustment_date": "2026-09-01",
					"is_cash_disbursement": 1,
					"cash_account": cash,
					"adjustment_type": "خصم",
					"description": f"FR170 concurrency {scenario}",
					"amount": 120,
					"side": "Supplier",
				}
			],
		)
		frappe.db.commit()
		row = next(r.name for r in card.adjustments if r.is_cash_disbursement)
		names[scenario] = {"card": card.name, "row": row}
		if scenario == "duplicate":
			continue
		frappe.set_user(USERS["requester"])
		payment = request_cash_disbursement(card.name, row, nowdate(), f"FR170 {scenario}")
		frappe.db.commit()
		names[scenario]["payment"] = payment
		frappe.set_user(USERS["manager_a"])
		approve_cash_disbursement(payment)
		frappe.db.commit()
		# approved (not yet queued) for the queue race; queued for the posting races
		if scenario in ("posting", "cancel_vs_posting"):
			queue_posting(payment)
			frappe.db.commit()
	frappe.set_user("Administrator")
	with open(_state_path(), "w", encoding="utf-8") as fh:
		json.dump(names, fh, indent=1)
	print("seeded", json.dumps(names))
	return names


def _load_state():
	with open(_state_path(), encoding="utf-8") as fh:
		return json.load(fh)


# ---------- scenarios ----------


def run_approval(names):
	from card.cash_disbursement import approve_cash_disbursement

	payment = names["approval"]["payment"]
	outcome = _race(
		[
			(USERS["manager_a"], approve_cash_disbursement, (payment,)),
			(USERS["manager_b"], approve_cash_disbursement, (payment,)),
		]
	)
	row = frappe.db.get_value("Card Cash Disbursement", payment, ["status", "approved_by"], as_dict=True)
	return {
		"scenario": "approval",
		"outcome": outcome,
		"final_status": row.status,
		"approved_by": row.approved_by,
		"passed": len(_ok(outcome)) == 1 and row.status == "Approved",
	}


def run_queue(names):
	from card.cash_disbursement import queue_posting

	payment = names["queue"]["payment"]
	outcome = _race(
		[
			(USERS["manager_a"], queue_posting, (payment,)),
			(USERS["manager_b"], queue_posting, (payment,)),
		]
	)
	row = _status(payment)
	return {
		"scenario": "queue",
		"outcome": outcome,
		"final_status": row.status,
		"passed": len(_ok(outcome)) >= 1 and row.status == "Posting" and not row.journal_entry,
	}


def run_posting(names):
	from card.cash_disbursement import execute_posting

	payment = names["posting"]["payment"]
	outcome = _race(
		[
			(USERS["service"], execute_posting, (payment,)),
			(USERS["service"], execute_posting, (payment,)),
		]
	)
	check = _check_entry_consistency(payment)
	return {
		"scenario": "posting",
		"outcome": outcome,
		**check,
		"passed": len(_ok(outcome)) >= 1
		and check["status"] == "Posted"
		and check["consistent"]
		and len(check["submitted_entries"]) == 1,
	}


def run_cancel_vs_posting(names):
	from card.cash_disbursement import execute_posting, request_cancellation

	payment = names["cancel_vs_posting"]["payment"]
	outcome = _race(
		[
			(USERS["service"], execute_posting, (payment,)),
			(USERS["manager_a"], request_cancellation, (payment, "FR170 race")),
		]
	)
	check = _check_entry_consistency(payment)
	# Cancellation is accepted only from Posted, so it either waits for the posting (then it may succeed) or it is refused.
	# In every order the final state must agree with the single submitted entry.
	return {
		"scenario": "cancel_vs_posting",
		"outcome": outcome,
		**check,
		"passed": check["consistent"]
		and check["status"] in ("Posted", "Cancellation Requested")
		and len(check["submitted_entries"]) == 1,
	}


def run_duplicate(names):
	from card.cash_disbursement import request_cash_disbursement

	card, row = names["duplicate"]["card"], names["duplicate"]["row"]
	outcome = _race(
		[
			(USERS["requester"], request_cash_disbursement, (card, row, nowdate(), "FR170 dup a")),
			(USERS["requester"], request_cash_disbursement, (card, row, nowdate(), "FR170 dup b")),
		]
	)
	count = frappe.db.count("Card Cash Disbursement", {"card": card, "adjustment_row": row})
	return {
		"scenario": "duplicate",
		"outcome": outcome,
		"payments_for_row": count,
		"passed": len(_ok(outcome)) == 1 and count == 1,
	}


def run_all():
	"""Run every scenario on its own committed records and print the summary (no entry is created twice)."""
	names = _load_state()
	results = [
		run_approval(names),
		run_queue(names),
		run_posting(names),
		run_cancel_vs_posting(names),
		run_duplicate(names),
	]
	summary = {"passed": all(r["passed"] for r in results), "results": results}
	print(json.dumps(summary, ensure_ascii=False, default=str))
	return summary
