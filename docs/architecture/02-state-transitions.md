# State transitions per DocType

Sources: the controllers under `card/card/doctype/<doctype>/`, `card/gl/events.py`, `card/gl/posting.py`,
`card/transfer.py`, `card/materials.py`, `card/equipment_status.py`, `card/period_lock.py`. CARD defines **no Frappe
Workflow** (`card/hooks.py` and `fixtures` ship none): every state below is a field or the standard `docstatus`
(0 Draft, 1 Submitted, 2 Cancelled), moved by controller code. That is a design fact to keep in mind for #51
(Planned: configurable roles and approvals).

Notation: `A -> B [who / guard]`. "Server" means the controller writes it; the client cannot.

## 1. Cross-cutting guards (apply to several DocTypes)

| Guard | Applies to | Source |
|---|---|---|
| Period lock: save, submit, amend, cancel and delete refused when the document date (or its stored date) is on or before `period_lock_date`; an override role bypasses it, and every bypass is logged and recorded as a Comment on the document (FR-123) | Card Monthly Card, Project Diesel Fill, Equipment Transport | `card/period_lock.py`, hooks `_PERIOD_LOCK_EVENTS` |
| Mandatory cancel reason (FR-123, #197): a cancel without a reason is refused, a cancel request that changes any other stored field or row is refused, and the reason is stored on `cancel_reason` and in a Comment. The form asks for the reason and calls `cancel_with_reason`; REST must send it with the cancel; a workflow cancel action and the list view's bulk cancel are refused by the server guard (no reason is sent); not covered by a dedicated test. Documents cancelled before FR-123 keep an empty reason | the same three | `card/cancel_reason.py`, `card/public/js/cancel_reason.js` |
| Held-source guard: a source in an active (Draft or Submitted) posting cannot be cancelled | the same three | `card/gl/events.py` `block_source_cancel` |
| Cancelled sources can be amended; an amended copy of a posted source is refused unless the posting was cancelled | the same three | `card/gl/events.py` `_block_amended_copy` |
| Equipment status guard: an ended machine gets no new assignment, transport or card; Warn only by default, Refuse per company | Assignment, Transport, Monthly Card | `card/equipment_status.py`, setting `equipment_status_rule` |
| Company isolation on read and write | all operational DocTypes | `permission_query_conditions` and `has_permission` in `card/hooks.py` |

## 2. Card Equipment (`status`, no docstatus)

Values: active (نشطة), stopped (متوقفة), under maintenance (في الصيانة), ended (منتهية).

```
active <-> stopped <-> under maintenance        any of the three -> ended
```

| Transition | Guard in code |
|---|---|
| Any value to any other | The field is editable; there is no transition table. Commercial changes need a reason (`validate_commercial_change_reason`) and fields at higher permlevels |
| To ended | Sets the rule of `equipment_status.py`: new assignment, transport and monthly card are warned or refused. A card whose period starts on or before the exit date (or a passed rental end) is exempt: it is the last work, not a new use |
| Out of ended | Not guarded. **Gap**: nothing stops an ended machine from being set active again; the history is in the Version log |

Location (`current_project`, `assignment_date`) is derived and read only: `keep_derived_location`, written by
`card.transfer.sync_equipment_location`.

## 3. Card Equipment Assignment (not submittable)

An open row has an empty `to_date`. There is no docstatus.

| Transition | Who / guard |
|---|---|
| Create (open) | Card Manager or a Transport on submit. Overlap with another assignment of the same machine is refused under a row lock (`validate_no_overlap`); company of equipment and project must match |
| Close (set `to_date`) | A Transport that moves the machine writes it (`card.transfer._apply_row_transfer`); or a Card Manager by hand |
| Shorten or delete | Refused if card days already recorded fall outside the new period (`_refuse_dropped_card_days`) |

Each create, close or delete re-derives the machine's current project.

## 4. Equipment Transport (docstatus plus `financial_status`)

```
Draft --submit--> Submitted --cancel--> Cancelled
                     |
                     +-- financial_status: No decision needed | Pending --> Approved | Rejected
```

| Transition | Who / guard | Effect |
|---|---|---|
| Draft to Submitted | Equipment status re-checked for every row; `submitted_by` written; period lock | `apply_transfer`: closes the machine's open assignment, opens a new one, syncs location. The move day belongs to the new project or the old one by the company's `move_day_rule` (empty means the day after, as before) |
| Submitted to Cancelled | A cancel reason is required (section 1). `check_cancel_allowed`: refused if a later transfer exists for a machine, if card days exist on the new project after the move, or if an assignment link was not written by this transport. A cancel cannot change the stored rows (`_refuse_changes_on_cancel`) | `reverse_transfer` undoes only what this transport wrote |
| `financial_status` to Approved or Rejected | `record_financial_decision`: Accounts Manager only, never the transport's creator, editor or submitter; row-locked; decision must fit the cost bearer (customer or equipment supplier) | Recorded only. Customer billing, supplier recovery and absorption postings are **not built** (see [05-accounting-examples.md](05-accounting-examples.md) section 6) |
| Edit after submit | Refused for the financial fields (`before_update_after_submit`) | |

A transport with a responsibility scenario recorded (`responsibility`, `payer` set) is excluded from the monthly
posting until decisions are made (`gl/posting.py` `_supplier_sources`).

## 5. Card Monthly Card (docstatus)

```
Draft --submit--> Submitted --cancel--> Cancelled --amend--> Draft (new name)
```

| Transition | Who / guard | Effect |
|---|---|---|
| Save (Draft) | Roles Card User, Card Manager, Accounts Manager. Days must fall in the month, no duplicates, no negative or future hours (operating or stopped), a day with stopped hours may not exceed 24 hours operating plus stopped (FR-118), a stop reason must be an enabled reason of the card's company, and, for a machine that has assignment history, inside an assignment period for the card's project (`card.transfer.validate_card_days`; a machine with no history is not constrained); project is derived from assignments | Totals and amounts recomputed by `before_validate`; direction mirrored from the equipment |
| Billing effect of a stop reason (FR-118) | Stopped hours count toward billing only when the day row's snapshot `reason_billable` is set (the reason's `billable`, default off); the card stores `billable_stopped_hours` and `billable_stopped_days`. With no billable reason every amount is what it was before | Derived on every save of a Draft |
| Draft to Submitted | A customer-billing card needs the equipment's customer (`before_submit`); period lock | `_snapshot_settings_used` stores the rates, daily hours, direction and customer used, so later changes do not move a submitted card; registry rows synced; optional notification |
| Submitted to Cancelled | A cancel reason is required (section 1); blocked while a Draft or Submitted posting holds the card (`block_source_cancel`); period lock | Registry rows re-synced; reason stored and commented |
| Posting flag `posted` | Server only: set on invoice submit, cleared when the last invoice that holds the card is cancelled (`gl/events.py`) | Display and guard |

The separation-of-duties rule "whoever created a card never approves it" is **Planned** (FR-006, #51). Today a card
is submitted by anyone with submit rights.

## 6. Project Diesel Fill (docstatus plus `review_status`)

`review_status`: Draft, Needs Review, Operations Approved, Rejected. `price_source`: Company Price, Exception, Needs
Review.

```
Draft --evidence warnings--> Needs Review --Card Manager--> Operations Approved --submit--> Submitted
   \________________________ Card Manager ________________> Rejected
Operations Approved --material edit by anyone--> Needs Review
```

| Transition | Who / guard |
|---|---|
| To Needs Review | Automatic when a Draft has warnings or an inconsistent totalizer (`_guard_review`) |
| To Operations Approved or Rejected | `Card Manager` or `System Manager` only (`REVIEW_ROLES`); approval needs the closing photo and reading; the reviewer is the session user |
| Material edit after approval | Any user's change to a reviewed field returns it to Needs Review (`REVIEWED_FIELDS`) |
| Draft to Submitted | Refused unless `review_status` is Operations Approved and the price is decided (`before_submit`) |
| Submitted to Cancelled | A cancel reason is required (section 1); blocked while a posting holds the fill; period lock | Reason stored and commented |
| Amendment | The cancelled fill's review is not inherited; the amendment starts at Draft |
| Posting | Imported WhatsApp sessions (`source_key` set) are never put into a CARD posting; their supplier's own invoice is entered separately (`gl/posting.py` `_supplier_sources`) |

Price: the price comes from the company schedule or settings and is locked; a different price needs an exception by a
role set in Card Settings, with a reason (`_check_exception`, FR-002).

## 7. GL Posting Log (`status`, no docstatus)

Values: Draft, Submitted, Cancelled, Failed (`Failed` is an allowed value; no code path outside tests sets it at this commit). `origin`: Built (by CARD) or Linked (hand-booked invoice or accrual).

```
(builder) Draft --invoice submitted--> Submitted --invoice cancelled--> Cancelled
Draft --invoice deleted or cancelled--> Cancelled
```

Only `card.gl.posting.build_monthly_posting` creates a log (`validate_builder_insert`), and afterwards it moves only
by `db_set` from `card/gl/events.py`. No user, role or share edits or deletes it. While Draft or Submitted it holds a
unique `posting_key` (company, party type, party, month, year; plus sequence for late sources), so a second active
posting for the same party-month-side cannot exist. Cancelled and Failed clear the key.

## 8. Purchase Invoice and Sales Invoice built by CARD

CARD does not own these states; ERPNext does. CARD hooks `card/gl/events.py` add:

| ERPNext event | CARD behaviour |
|---|---|
| `validate` | Discount edits on a CARD-built invoice are refused (use card adjustments) |
| `before_submit` | Re-checks the build signature, company, month, period, sources total and supplier bill number; a VAT-registered supplier needs Bill No and Bill Date; an invoice CARD did not build may not repeat a CARD posting |
| `on_submit` | Writes the invoice link and `posted` on every source; log to Submitted |
| `before_cancel` | Frees the sources; log to Cancelled |
| `on_trash` (draft) | Frees the sources; log to Cancelled |

## 9. Equipment Needs Request, Equipment Needs Review

Request `review_status`: Pending, In review, Approved, Rejected. Review `approval_status`: Pending, Approved.

```
Request: Submitted/Pending --review submitted--> In review --review approved--> Approved (or Rejected if no line approved)
         In review --review cancelled--> Pending
Review:  Draft --submit--> Submitted/Pending --approve_review--> Approved
```

| Transition | Who / guard |
|---|---|
| Request status | Server only: `validate` resets it to Pending; the review and the approval move it (`equipment_needs_review.py` `_set_requests`, `materials.approve_review`) |
| Review approve | `approve_review`: Card Manager; not the person who prepared, edited or submitted the review (no role exempt); every approved line matched to an Item; tools need the tool store and a worker |
| Effects of approval | Draft Material Requests (one per type), a draft custody Handover per approved tool line. No stock moves |
| Review cancel | Refused after approval or once a Material Request exists |

## 10. Employee Tool Custody (docstatus plus `handover_status`)

Movements: Handover, Return, Transfer, Loss, Damage. `handover_status`: Awaiting handover, Handed over, Not handed over.

| Transition | Who / guard | Effect |
|---|---|---|
| Draft handover created | Server, on review approval or `make_handover_draft` | Waits for the store side |
| Submit | Under row locks; a Handover or Return needs the user's own Stock Entry submit right and a different confirmer from the worker, requester and enterer; Handover and Transfer need a signed private receipt; movement out needs a sufficient balance | Handover and Return: a submitted Material Transfer Stock Entry in the same transaction. Loss and Damage: a draft Material Issue left for the stock team. Partial handover leaves the rest in a new draft |
| Cancel | A confirmed Handover or Return cancels its own Stock Entry in the same transaction; a later movement that uses the tools blocks it | Quantity returns to the review line |

## 11. Card Equipment Part (fitment) (`compatibility_status`, `review_stage`, `is_active`)

Status: Pending Technical Review, Confirmed, Not Compatible. Stage: empty or Pending Second Review.

| Transition | Who / guard |
|---|---|
| Card Supervisor | Proposes and documents own pending rows only; cannot decide |
| Card Manager decides | Needs evidence source and reference; a machine row Confirmed against a model row Not Compatible needs a technical note |
| Proposer decides own row | Stored as a first review (reason and evidence file required) and the row stays Pending Second Review until another Card Manager decides; no final self-approval |
| New evidence on a decided row | Resets to Pending Technical Review |
| Retire or restore | Card Manager with a reason; a restored row is reviewed again |

## 12. Not implemented (Planned)

| Lifecycle in #40 | Issue |
|---|---|
| Configurable approval workflow and roles per company, audit of approvals | #51, #35 |
| Period approval before billing (HRMS Payroll Entry pattern) | #49 |
| Daily log operator, supervisor, manager | FR-022 (mobile) |
