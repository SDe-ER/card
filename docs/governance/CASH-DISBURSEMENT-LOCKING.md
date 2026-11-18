# Cash disbursement: transaction locking order

Scope: `card/cash_disbursement.py` (FR-170). Record types: `Card Monthly Card` (the card, "Card"), `Card Cash Disbursement`
(the payment, "CCD"), and the `Journal Entry` the executor creates. Database: MariaDB InnoDB, REPEATABLE READ (Frappe
default). Locks are taken with `frappe.db.get_value(..., for_update=True)`, a locking read (`SELECT ... FOR UPDATE`).

## Rules

1. **A locking read is the first database access of every state-changing action.** A plain read first would establish the
   transaction's consistent-read snapshot before the lock is granted, and later plain reads could then miss rows another
   transaction committed while this one waited.
2. **Order: Card first, then CCD.** When an action needs both, it locks the card row before any payment row.
   The one exception is the Replacement action, which locks the cancelled CCD row first and then its card row. This is
   safe, because no other action holds a card row while waiting for a CCD row (see the table below).
3. **Refusals are uniform.** A missing name and a record of another company raise the same `PermissionError` with the same
   text (`_refuse_payment`). Company checks run on the locked record, before any state is read or written.
4. **Database uniqueness is the last guard**: `transaction_key` (card, row, status-independent) and `journal_entry` are unique.

## Lock order per action

| Action | Locks taken (in order) | Plain reads after the locks | Writes |
|---|---|---|---|
| Request (`request_cash_disbursement`) | Card row (locking read) | Card, the duplicate check on (card, row) | Insert one CCD (Pending); unique `transaction_key` |
| Approve (`approve_cash_disbursement`) | CCD row | CCD, the accounting period | CCD -> Approved |
| Queue (`queue_posting`) | CCD row (locking read, status and journal entry) | CCD | CCD -> Posting |
| Execute (`execute_posting`, service identity) | CCD row (locking read) | Card (source revalidation, no lock needed: rows the executor only reads) | Journal Entry insert and submit; CCD `journal_entry` link, then CCD -> Posted |
| Cancel request (`request_cancellation`) | CCD row | CCD, the allocations | CCD -> Cancellation Requested |
| Cancel of the Journal Entry (ERPNext, human) | Journal Entry row (ERPNext), then the CCD row by the hook | CCD | JE -> cancelled; CCD -> Cancelled |
| Replacement (`request_replacement`) | CCD original row, then Card row | Card, the live-replacement check (locking read on (card, row)) | Insert one replacement CCD (Pending), linked by `replaces` |

## Deadlock analysis

Two lock orders can form a cycle only if one action holds a lock the other waits for while the other holds the first.

- **Card -> CCD** (Request): the request holds the card row and inserts a new CCD. It does not wait for any existing CCD row
  lock. It can wait only for a uniqueness conflict on a not-yet-committed insert of the same `transaction_key`, which is
  impossible because every request for one card row serialises on the card lock.
- **CCD -> Card** (Replacement): the replacement holds the original CCD row and waits for the card row. Its only waiter is
  a request, which holds the card row and does not wait for the original CCD row. No cycle.
- **CCD -> ERPNext Journal Entry** (Execute, Cancel): both take the CCD row first. The Journal Entry is taken after it.
  Cancel of a Journal Entry from ERPNext reaches the CCD row through the hook, which is the same order. No cycle.
- **Monthly posting builder** (`card/gl/posting.py`): it locks card rows and creates invoices. It does not lock CCD rows.
  A cycle would need the builder to wait for a CCD row, and it does not.

Result: no cycle is possible between the Monthly Card and Cash Disbursement locks in the current code.

## Verification status

- The lock order above is verified against the source (grep and read of the actions). The two-connection tests of
  `card/tests/concurrency_cash_locking.py` exercise approval, queue, posting, cancel and duplicate requests on committed
  synthetic records. Their results are recorded per commit in the FR-170 evidence folder, not here.
- Replacement against a second cancelled payment on the same card row is covered by the lock on the card row by reasoning
  only; it is not exercised by a concurrency test yet (outstanding).
