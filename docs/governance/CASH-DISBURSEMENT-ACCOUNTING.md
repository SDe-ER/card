# Owner-paid cash disbursement: accounting design and controls (FR-170 step 2)

Status: **Implementation in review, not released.** Evidence levels: SOURCE (code read), TEST (CI run on a named
commit), UNVERIFIED (not yet proven). Target version: unassigned until release preparation (SemVer, FR-170 depends on
the released version of record at that time).

## 1. Business event

A cash expense on a monthly card is paid by the company in cash on behalf of the equipment's owner (a Supplier the
card keeps as its beneficiary). The payment is not an invoice line of the rental invoice. Owner decision 2026-11-16:
it is posted by a standard Journal Entry at the approved payment, not by the monthly invoice.

## 1a. Accounting rationale for the Journal Entry (owner decision 2026-11-17)

This transaction represents a recoverable cash payment on behalf of a beneficiary. It is not an additional rental
expense and not a second payment of an existing invoice. For verified external Suppliers:

- Debit: Supplier Accounts Payable (the beneficiary's party account, `get_party_account`).
- Credit: the approved Cash account.

The subsequent reconciliation allocates the existing Supplier debit against eligible rental Purchase Invoices. It
creates no further cash movement. Journal Entry is the document type of this implementation; a change of document type
requires the evidence of section 7 and the owner's explicit approval.

## 2. Accounting entries

| Event | Document | Effect |
|---|---|---|
| Request on a Draft card | `Card Cash Disbursement` (CCD), Pending | none (no ledger effect) |
| Approval by a Card Manager other than the requester | CCD Approved | none |
| Queue (Approved -> Posting, row lock) | CCD Posting | none |
| Execution by the accounting service identity | Journal Entry, submitted | Dr Supplier payable (party = beneficiary Supplier, `get_party_account`), Cr the validated Cash account |
| Cancellation request (Card Manager, reason) | CCD Cancellation Requested | none |
| ERPNext cancels the Journal Entry | Journal Entry cancelled (reversal GL, standard) | reverses the entry; CCD becomes Cancelled |
| Replacement request | new CCD Pending, `replaces` = cancelled CCD | none until approved and executed |

CARD never writes GL Entry rows. Every ledger effect is an ERPNext document created by the executor.

## 3. Controls

- **Segregation:** requester != approver (`approve_cash_disbursement`); the Card Manager cannot execute the posting
  (`execute_posting` runs only under `SERVICE_ROLE`; tests in `test_cash_disbursement_post.py`).
- **Identity:** the executor runs as the dedicated identity `Card Cash Posting Service`. No code changes the session
  user, and enqueue is not used (enqueue records the requesting job user; frappe/utils/background_jobs.py, version-16).
  Production identity creation needs separate owner approval.
- **Exactly once:** a unique `transaction_key` (SHA-256 over card, row, amount, date, cash account, and the
  replacement revision) and a unique `journal_entry` link; a retried or interrupted run returns the existing entry.
- **Immutability after approval:** the economic fields (company, supplier, card, adjustment row, amount, payment date,
  cash account), `status`, `evidence`, the journal link and the approval/posting stamps cannot change through a
  normal save. The only controlled transition is the cancellation request (`request_cancellation`, a server flag not
  settable from a request). Delete is refused unless Pending.
- **Company scope:** `has_cash_disbursement_permission` applies Company User Permission on every read and write path.

## 4. Closed accounting periods (ERPNext behaviour, source evidence)

ERPNext version-16 refuses a Journal Entry in a closed Accounting Period in two places:

1. `erpnext/accounts/doctype/accounting_period/accounting_period.py`: `validate_accounting_period_on_doc_save`
   (registered on save for the period-closing doctypes in `erpnext/hooks.py`) raises `ClosedAccountingPeriod`.
2. `erpnext/accounts/general_ledger.py`: `validate_accounting_period` raises `ClosedAccountingPeriod` with the text
   "You cannot create or cancel any accounting entries ...". It is called when GL entries are created and, through the
   reversal path, when they are cancelled.

Only an exempted role of the period bypasses this. The service identity does not hold such a role.
Tests: `test_a_closed_accounting_period_refuses_the_posting` and `test_a_closed_accounting_period_refuses_the_cancellation`
(`test_cash_disbursement_post.py`). Status: TEST pending on the commit that adds them.

## 5. Reconciliation semantics (Payment Ledger Entry, ERPNext version-16)

Source: `erpnext/accounts/utils.py` (`delink_original_entry`, the ledger rows created for GL entries) and
`erpnext/accounts/doctype/payment_reconciliation/payment_reconciliation.py`.

| Row kind | Shape | Counts as allocation? |
|---|---|---|
| Original entry | `voucher_no` = `against_voucher_no` | no |
| Active allocation | the other document on one side, `delinked = 0` | **yes** |
| Delinked / reversed | `delinked = 1` (set by cancellation or unreconciliation) | no |

Cancellation of the Journal Entry is gated by CARD on active allocations (`_has_active_allocations`), because ERPNext's
own `on_cancel` ignores `Payment Ledger Entry` and `Unreconcile Payment` in its backlink check (journal_entry.py).
Without the gate an allocated entry could be cancelled and leave the invoice inconsistent.

Expected behaviour (tests in `test_cash_reconciliation_erpnext.py`, CI pending):

| Entry state | Cancellation |
|---|---|
| Unreconciled | allowed after an authorized request |
| Partially reconciled (payment larger than invoice) | blocked |
| Fully reconciled (payment smaller than invoice) | blocked |
| Reconciled, then unreconciled with the standard Unreconcile Payment | allowed; the invoice outstanding and the Supplier ledger return to their prior balances |

## 6. Replacement after cancellation

`request_replacement` (server side, Card Manager):
- only for a Cancelled payment; refused while the original is Posted or otherwise live;
- locks the original row before the live-replacement check (one active replacement per cancelled payment);
- creates a Pending payment with `replaces` = original and a new transaction key (revision = original name);
- approval must be by a different Card Manager than the requester;
- the original payment and its cancelled Journal Entry are not changed.

Known gap: `replaces` is not a unique database index (empty links may be stored as empty strings on this version), so the
one-active-replacement rule relies on the row lock plus the live check, not on the database.

## 7. Payment Entry versus Journal Entry

Workspace rule (`AGENTS.md` section 6): supplier payments use Payment Entry; Journal Entry is an exception and needs an
explicit rationale.

| Aspect | Journal Entry (implemented) | Payment Entry (alternative) |
|---|---|---|
| Owner decision | Yes (2026-11-16) | no |
| Shape | Dr payable (party), Cr cash | paid_from = cash, party = Supplier, payment type Pay |
| Invoice reference at payment time | none: the cash expense is not an invoice of the rental | none, so the Payment Entry would be unallocated |
| Reconciliation | Payment Reconciliation (standard) | Payment Reconciliation (standard) |
| Cancellation | standard JE cancel, gated by CARD | standard PE cancel; ERPNext also unlinks references |
| Repo evidence | CARD tests for JE posting and reconciliation | `card/tests/test_payment_entry_parity.py` (customer side, native Payment Entry) |

Assessment: both documents post the same ledger effect. The Journal Entry follows the owner decision and carries its
rationale (an owner-paid expense with no invoice reference). A Payment Entry would be the default under section 6 of the
workspace contract, so the rationale must be recorded in the decisions register before release. Changing the document
type needs owner approval; this assessment does not change it.

## 7a. Operational workflow (implemented)

| Step | Who | Endpoint or action | Result |
|---|---|---|---|
| Request | Card User (write on the card, company checked) | `request_cash_disbursement` (POST), Monthly Card action "Request cash approval" | one Pending payment for the cash row; duplicate refused |
| Submit the card | the card owner | normal Monthly Card submission | independent: a Pending payment does not block it; the row stays linked and in no total |
| Approve | Card Manager other than the requester | `approve_cash_disbursement` (POST) | Approved; approver and time recorded |
| Queue | Card Manager (company checked) | `queue_posting` (POST) | Posting (atomic claim under a row lock); a failed payment may be queued again |
| Dispatch | the accounting service identity only | `run_posting_queue` (POST) | each queued payment posted in a savepoint: one submitted Journal Entry, or Posting Failed with the error |
| Reconciliation | an accountant | ERPNext Payment Reconciliation / Unreconcile Payment | reconciliation status shown separately (Not / Partially / Fully reconciled) |
| Cancellation | Card Manager requests; an accountant cancels the Journal Entry | `request_cancellation` (POST), then ERPNext cancel | Cancelled; no repost |
| Replacement | Card Manager requests; a different Card Manager approves | `request_replacement` (server side), then the same flow | a new payment linked by `replaces`; posted once |

### Status model (two separate dimensions)

- **Posting status** (the payment): Pending approval, Approved, Queued for posting, Posting failed, Posted,
  Cancellation requested, Cancelled.
- **Reconciliation status** (only for a posted payment, from the active allocations in the Payment Ledger Entry):
  Not reconciled, Partially reconciled, Fully reconciled.
- **Replacement pending**: a Pending payment whose `replaces` is the cancelled payment.

### Executor dispatch (no enqueue, no identity switch)

- `run_posting_queue` is a whitelisted POST. Only the dedicated service role may call it; otherwise a permission error.
- Candidates are limited to the caller's permitted companies, checked on each row (a payment of a company the
  identity is not permitted for is not selected).
- Each payment is posted inside a savepoint. A failure rolls back that payment only and records `Posting Failed` with
  the error. A retry is a new queue claim followed by the same dispatch; `execute_posting` finds an entry an earlier
  run already created (by its remark) and links it instead of creating a second one.
- Every posting records who requested, who approved, who claimed and who posted (`posted_by`), and the entry's remark
  carries the requester and the approver.
- Production: the service identity, its token and its runner are not provisioned. Creating them needs the owner's
  explicit approval. Tests create the identity in the test site only.

### Verification

- `test_cash_operational_workflow.py`: one scenario through the real endpoints (request as Card User, submission while
  pending, approval by another Card Manager, dispatch as the service identity through `frappe.call`, ERPNext
  reconciliation and unreconciliation, accountant cancellation, replacement posted once). Ledger balances come from
  ERPNext `get_balance_on`; invoice outstanding from the Purchase Invoice.
- `test_cash_disbursement_post.py`: dispatch refused to a Card Manager; a disabled Cash account makes the real Journal
  Entry insert fail: the attempt is rolled back, the payment is Posting Failed, the retry posts exactly one entry.
- `test_bola_matrix.py`: cross-company refusal for the request, the status read, the queue and the dispatch endpoints
  (fixtures for the access-control checks only; positive transitions are tested through real records).

### 7b. Where the cash payment is managed (FR-170 step 4)

The Additions and deductions table of the Monthly Card is the only operational place: a cash payment is a cash row
of the table (`is_cash_disbursement`, cash account, date, amount). The row shows its payment status and its journal
entry (read-only columns, refreshed from the payment record); the actions sit in the card's Cash payments menu. Every
action calls the existing server method, which checks the role, the company and the state again.

Accounting effect of each step (unchanged backend rules):

- Request, approve and queue create no ledger entry. Approval is refused for the requester.
- Execute (service identity only) creates one submitted Journal Entry: Dr the Supplier payable, Cr the Cash account.
- The rental Purchase Invoice does not include the cash row (no duplicate deduction). Its outstanding balance is
  reduced only when ERPNext's Payment Reconciliation allocates the Journal Entry to it.
- A cancellation request changes no ledger entry. The accountant cancels the Journal Entry in ERPNext after
  unreconciling it; the payment then shows Cancelled.
- A replacement is a new Pending payment linked to the cancelled one. It is approved by a different Card Manager and
  posted once by the service identity. The cancelled entry stays cancelled, so the financial effect appears once.

Verified on the isolated QA site (synthetic data): the sequence request, approval by a second Card Manager, queue,
posting (one entry), cancellation, accountant cancel of the entry, replacement, approval, queue and posting (one
further entry). The card shows one active journal entry at the end.

## 8. Known limits and unverified items

- Runtime proof of the reconciliation tests and the closed-period tests is pending CI on the commit that adds them.
- The executor runs in tests as the service identity inside the test site; a production runner and identity are not built.
- No Desk button for approve, queue or execute is exposed yet (server-side functions only).
- Currency: the flow is single-currency (company currency).
- Rollback: revert the code; posted and cancelled entries remain as ERPNext documents.

## 9. Security review of the cash workflow (FR-170)

### 9.1 ignore_permissions sites introduced by FR-170

| Site | Why ignore_permissions | Explicit authorization that replaces the document right |
|---|---|---|
| `card/cash_disbursement.py` `request_cash_disbursement`: insert of the payment record | The payment DocType grants create to Card Manager only, and a Card User must be able to request from the card. | The caller must have write on the Monthly Card (`check_permission("write")`, its company checked). The row is revalidated: it must be a cash row; the amount and the Cash account come from that row, never from client input; the Supplier is the card's stored beneficiary; the evidence and the payment date are validated; one payment per row. |

No other FR-170 code uses ignore_permissions. The allowlist entry is not an approval: the explicit authorization above is.

### 9.2 Executor (dispatch) checks, per record

1. The caller is the dedicated service role (`run_posting_queue`); anything else is a permission error.
2. Candidates are limited to the caller's permitted companies, checked on each row (Company User Permission).
3. Only status Posting (an approved and queued payment) is processed.
4. `execute_posting` checks the company again (`has_cash_disbursement_permission`).
5. The source is revalidated before any entry is built: the card row is still a cash row, its amount and Cash account
   equal the approved values, the Supplier is still the card's beneficiary, and the company matches. A change is refused
   (Posting Failed; no entry). Test: `test_the_executor_refuses_a_source_changed_after_approval`.
6. The Journal Entry is created once (unique payment link; remark lookup for an interrupted run); the posting records
   the identity that posted (`posted_by`), the claimant, the approver and the requester.

No document right is granted to the service role on the payment DocType (a Custom DocPerm would replace the DocType's
matrix for every role; this was found and removed in CI).

### 9.3 Immutability after approval

The economic fields (company, supplier, card, adjustment row, amount, payment date, Cash account), the status, the
evidence, the transaction key, the Journal Entry link, `replaces`, the approval and posting stamps, the posting error and
`posted_by` cannot change through a normal save. The controlled cancellation request is the only transition allowed
from Posted, and it is a server-side flag that a client request cannot set.

### 9.4 Accounting regression protection

- A pending cash row is excluded from the card's additions, deductions and supplier net
  (`test_a_pending_cash_row_is_in_no_card_total_and_no_net`).
- The invoice-line builder skips the cash row, so the lines match the stored net; without this a submit was refused
  (`Reconciliation mismatch`, found in CI on 943bf7f).
- The Supplier invoice consistency check at submit is the regression guard for lines against totals.

### 9.5 Open findings (not yet closed)

- The Customer-side and settlement-report and period-run fingerprint exclusions are covered only by the shared
  totals and the invoice identity check; there is no dedicated test for each report yet.
- The service identity is a test identity. A production identity, its token and its runner need owner approval.
- The HTTP dispatch (a request with the identity's token) is not yet verified in a non-production environment.
- Code Review and Security Review have not been run on the final commit.


### 9.6 Findings resolved in this change

- **Finding 1 (fail-open company authorization), fixed.** `executor_companies()` reads only the identity's explicit
  Company User Permission rows and returns an empty set when there are none. `run_posting_queue` selects candidates
  with those companies in the query and returns nothing for an empty grant. `execute_posting` takes the grant as a
  required argument and checks the payment's company before any write. A payment outside the grant is never marked
  failed. Tests: no grant, one grant, several grants, cross-company denial, and no entry for an ungranted company.
- **Finding 2 (forgeable journal-entry linkage), fixed.** The executor no longer searches entries by remark. The
  durable link `Card Cash Disbursement.journal_entry` (unique in the database) is written in the same transaction
  that creates the entry, before submission. Recovery follows only that link and validates the entry: not cancelled,
  the payment's company, created by the executing identity, one Supplier debit to the payment's party account at the
  approved amount, one credit to the approved Cash account at the approved amount. The remark is audit text only.
  Tests: forged remark with a wrong amount; with a wrong Supplier; a linked entry with mismatched fields refused;
  interruption before submit (nothing left, then retried); recovery of a linked draft (submitted once); repeated and
  concurrent dispatch (one entry). The two-connection race is not reproducible in the single-connection suite.
