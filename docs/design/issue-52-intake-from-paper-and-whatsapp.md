# Issue 52: intake from paper and WhatsApp — design

**Status: design. The slice of section 4 is built as FR-189 (In review); every other part is design only.**
Baseline: `main` @ `b27be391` (2026-11-25). Every code claim in sections 1 to 3 was read at that commit, before
FR-189.

Issue #52 carries the label `deferred` (owner comment of 2026-11-24, and the last-but-one row of the decision table
in [08-roadmap.md](../architecture/08-roadmap.md)). The owner instruction of 2026-11-25 supersedes that note for
this document and for the slice of section 4: "write the design doc, implement what is concrete behind a setting
defaulting OFF". The issue label and the roadmap row were not changed.

This document builds on [INTAKE-PROVENANCE-DESIGN.md](../governance/INTAKE-PROVENANCE-DESIGN.md), called "the base
design" below. It does not repeat the base design. Where the two differ, section 3 says so.

Terms used here:

- **Evidence**: the original paper sheet (scan or photo) or the WhatsApp message (screenshot or exported text).
- **Intake record**: a Card record that a person typed from evidence.
- **Enterer**: the user who created or edited the draft.
- **Reviewer**: the user who approves the record. For a transport, the approval is the submit.

## 1. Scope of the issue, item by item

Status words: **Implemented** (code on `main`), **Partly**, **Not implemented**.

### 1.1 Requirements

| # | Requirement of #52 | Status | Evidence in the code |
|---|---|---|---|
| R1a | Transport: enter one time from evidence. Keep the file, source, received time and operator | Implemented (FR-146) | `card/intake.py` `apply_transport_intake`, `_set_evidence_hash`, `claim_transport_evidence`. Fields `intake_channel`, `intake_source_key`, `intake_received_on`, `intake_evidence`, `intake_evidence_hash` in `equipment_transport.json`. Operator = `owner` plus `edited_by` (`EquipmentTransport._record_editor`) |
| R1b | Monthly card day: same | Partly (FR-158) | `card/intake.py` `apply_card_day_intake`. Fields `intake_source`, `intake_source_key`, `intake_received_on`, `intake_evidence_hash` in `card_monthly_card_day.json`. There is no evidence file field on the day row. `set_card_day_evidence_hash` has no caller in `card/` outside tests, so the hash stays empty for a hand entry |
| R1c | Diesel fill: same | Partly (FR-085, FR-086) | Imported sessions keep `source_key`, `source_messages`, `source_caption` (`card/diesel_import.py` `_new_fill`). A hand-entered fill keeps the meter photos (`opening_photo`, `closing_photo`, `ProjectDieselFill._check_photos`) but has no channel and no received time. `ProjectDieselFill._guard_source` refuses the source fields on a hand entry |
| R1d | Other records (Diesel Dispense, Equipment Meter Reading, Card Daily Log) | Not implemented | Attach fields exist (`diesel_dispense.json` `evidence_attachment`, `equipment_meter_reading.json` `attachment`). No channel, key or received time. Their validation was not verified for this document |
| R2 | Import, assistant or portal adapters propose records through the same validation, duplicate check, permission and approval as a hand entry | Partly (FR-086) | Only diesel: `card/diesel_import.py` `import_sessions` (role check, `frappe.has_permission`, `doc.insert()`, never submits). `card.intake.propose` does not exist. DocType `Card Intake Record` does not exist. Its name is only reserved in `card/hooks.py` `_COMPANY_SCOPED` and `card/company_scope.py` (FR-131) |
| R3 | No mandatory external AI or cloud service. Manual entry always possible | Implemented | Every intake field is typed by a person. The only automatic reader is the local meter worker (FR-101). It is off unless the site config holds `card_meter_worker_url` and `card_meter_worker_token` (`card/diesel_meter_extraction.py` `worker_config`), and `check_worker_url` accepts only a loopback or private IP address |
| R4 | Fill derived project, supplier, contract, price, fuel rate and accounting dimensions. Show exceptions for review, never guess | Partly | Diesel price: `ProjectDieselFill._apply_price`, field `price_source` = `Needs Review`. Transport price and cost center: `EquipmentTransport._apply_transport_price`, `_apply_destination_cost_center`, `_resolve_responsibility`. Imported diesel equipment stays as `reported_name` with `match_status` = `Unmatched` (`diesel_fill_equipment.json`). There is no single list of intake exceptions. The function names were verified. Their full behavior was not verified again for this document |

### 1.2 Acceptance cases

| # | Case | Status | Evidence in the code |
|---|---|---|---|
| A1 | Duplicate message or photo | Implemented per record type | Transport: `card.intake.check_source_key` refuses a second live transport with the same company and key. `warn_reused_evidence` warns for the same file. Card day: `_check_day_intake_dedupe`. Diesel: unique `source_key`, `ProjectDieselFill._check_photos`, `diesel_import._check_unused`. No check across record types |
| A2 | Missing values | Partly | The record stays a draft and its own `validate` runs. A diesel fill with warnings gets `review_status` = `Needs Review` (`ProjectDieselFill._guard_review`). A transport has no "needs review" state for its intake |
| A3 | Conflicting project or date | Partly | Diesel: `ProjectDieselFill._check_equipment_on_project` with the company setting `diesel_fill_project_check`. Transport: `EquipmentTransport._validate_project_company`. A received time in the future is refused (`apply_transport_intake`, `_normalise_day_intake`). No check compares the event date with the received time |
| A4 | Unauthorized sender | Not implemented | Card stores no sender. The only control is the Card permission of the enterer |
| A5 | Partial import and retries | Implemented for diesel import only | `diesel_import._import_one`: one savepoint for each session, `_remove_files` on failure, a second run returns `Existing` |
| A6 | Audit logs | Partly | `track_changes` = 1 on `equipment_transport.json` and `project_diesel_fill.json`. Submitted intake fields are frozen (`card.intake.freeze_submitted_intake`, `freeze_submitted_card_day_intake`). Evidence of a submitted or cancelled transport cannot be deleted, moved or made public (`keep_transport_evidence`, `keep_transport_evidence_file`, `keep_evidence_of_deleted_transport`). No hook in `card/hooks.py` `doc_events["File"]` protects the meter photos of a submitted diesel fill. Evidence that was received and then rejected leaves no record |

### 1.3 Items from the owner context

| # | Item | Status | Evidence in the code |
|---|---|---|---|
| C1 | A different person reviews an intake record | Not implemented for transports and diesel fills | `EquipmentTransport.before_submit` writes `submitted_by` and does not compare it with the enterer. `ProjectDieselFill._guard_review` checks the role (`REVIEW_ROLES`) and does not compare the reviewer with `owner`. Monthly cards have this rule: `card.governance.before_submit` with the company setting `card_approval_rule` (FR-143) |
| C2 | Upload of evidence from Card Mobile | Not implemented | `card/mobile.py` has one whitelisted method, `get_session_context` (read only). A search of `frontend/src` for "upload" and "attach" found nothing |
| C3 | Retention period of evidence | Not implemented | No retention rule in `card/`. Evidence of a submitted transport is kept without limit (A6) |
| C4 | OCR or other automatic reading | Not implemented, except the local meter worker of R3 | See R3 |

### 1.4 Registry differences found (not changed by this document)

- FR-146: the Open points column says "Not merged", but the code is on `main` (`card/intake.py`, `card/hooks.py`).
- FR-158: status "In review", but `card/hooks.py` calls `card.intake.apply_card_day_intake` on `main`.
- FR-131 has two rows with different statuses.

A separate registry correction must fix these rows.

## 2. Proposed answers to the open questions

The first four questions are section 10 of the base design. The others come from the issue and the owner context.

| # | Question | Proposed answer | Business reason |
|---|---|---|---|
| Q1 | Which channels and record types first? | Paper and WhatsApp only, typed by a person. Order: transports (done), then diesel fills, then monthly card sheets | Transports and diesel are single events with one piece of evidence. A monthly sheet has many days and needs more screen work |
| Q2 | May the enterer also approve? | The company decides. Default: yes, as today. When the company turns the rule on, a different person must approve (section 4) | A small office with one manager must not be blocked. A larger office gets a real second check |
| Q3 | Monthly card: one source for each day or for each sheet? | For each sheet. The sheet file is attached one time to the card. Each day row points to it with `intake_source_key` (the sheet number) | The site sends one sheet for many days. One file is easier to find and uses less storage |
| Q4 | How long is evidence kept? | Keep it. No automatic deletion. A later deletion is a manual act with owner approval, and never for a submitted or cancelled record | Evidence is the proof behind supplier and customer amounts. An automatic delete can remove proof that is still necessary. The number of years is an owner decision (section 5) |
| Q5 | Who uploads evidence? | The office users who can already create the record: Card User and Card Manager, on the Desk form. No upload from Card Mobile now | No new permission. An operator upload needs a new grant and a new endpoint, which is a separate owner decision |
| Q6 | Who reviews? | The users who can already submit: Card Manager and System Manager (`equipment_transport.json` permissions). Diesel: the existing operations review roles (`REVIEW_ROLES`) | No new role. The review stays inside the existing approval step |
| Q7 | Which record types? | Equipment Transport, Project Diesel Fill, Card Monthly Card day rows. Other types only on request | These three hold the supplier and customer amounts |
| Q8 | What happens with a duplicate? | Same key in the same company: refused (today). Same file on a second record: warning only (today). Keep both | One sheet can list several moves, so a refusal of the same file is wrong in real use. The key is the control |
| Q9 | What does "provenance" store? | Channel, a reference typed by the office (sheet number or message date and time), the time the office received it, the private file, the file fingerprint (SHA-256), the enterer, the reviewer. No phone number and no sender name | The office user is accountable for the entry. Sender phone numbers are personal data and add no control (answers A4) |
| Q10 | Unauthorized sender? | Not a system check. The enterer decides if the source is valid before he types it. The reviewer sees the evidence | With manual entry, a person reads every message. A sender list is useful only with an automatic WhatsApp link, which is out of scope |
| Q11 | Does Card need the `Card Intake` register of the base design now? | No. Keep the fields on the records (as FR-146 and FR-158 did). Add the register only when an import adapter is approved | A register without an adapter adds a screen and a permission set that nobody uses |

## 3. Proposed design for the parts not implemented

Principle: reuse the fields and guards that exist. Add no DocType. Add no permission. Each part below is a
separate change with its own owner GO, branch, tests, CHANGELOG entry and registry row.

### 3.1 Parts

| Part | Closes | What it adds | Reuses |
|---|---|---|---|
| P1 | C1 for transports | Second-person rule at submit, by company, default off (section 4) | `intake_*` fields, `owner`, `edited_by`, `submitted_by` of Equipment Transport |
| P2 | C1 for diesel fills | The same rule in the operations review: the reviewer is not the `owner` of the fill. Same company setting as P1, or a second one (design choice at build time) | `ProjectDieselFill._guard_review`, `ops_reviewed_by` |
| P3 | R1c | Two optional fields on Project Diesel Fill for a hand entry: `intake_channel` and `intake_received_on`, same names and options as the transport. The import-only `SOURCE_FIELDS` stay as they are | `card.intake.CHANNELS`, the meter photos as evidence |
| P4 | A6 for diesel | File guards for the meter photos of a submitted or cancelled fill, same rules as the transport evidence | Pattern of `card.intake.keep_transport_evidence` and `keep_transport_evidence_file` |
| P5 | R1b, Q3 | Sheet evidence on a monthly card: one private file for each sheet on the card, and the server computes `intake_evidence_hash` of the day rows that name the sheet | `set_card_day_evidence_hash`, `card.intake.file_sha256`, `card.attachment_validator` |
| P6 | A2, A3, R4 | A read-only report "Intake records to review": draft records with an intake channel, their warnings and their age | Existing fields only. Report access follows the record permissions |
| P7 | R2, A5 | The `Card Intake Record` register and `card.intake.propose` of the base design. Only with an approved adapter | Base design sections 3 to 5, FR-131 company scope |

P5 and P6 change the Desk form or add a page. They need before and after fixture diffs and owner approval before
any build (repository rule for UI changes).

### 3.2 Data

- P1 adds one Check field to `Card Company Settings` and one hidden, server-written Check field to
  `Equipment Transport` (`intake_declared`, added after the security review of the slice).
- P3 adds two fields to `Project Diesel Fill`: optional, empty by default, `no_copy`.
- P5 needs one place for the sheet file. Proposal: a small child table on `Card Monthly Card` (sheet number, private
  file, server-written hash). This is a new child DocType and the only one in this design. It is not final.
- P7: see the base design. Nothing new here.

### 3.3 States

No new status field for P1 to P4.

```
Transport:    Draft (enterer) --submit by a reviewer--> Submitted --> Cancelled
Diesel fill:  Draft / Needs Review --operations review--> Operations Approved --submit--> Submitted
```

A record typed from evidence is a draft. It has no effect on assignments, statements or accounting documents until
it is submitted. With the rule off, the enterer can submit, as today. With the rule on, the server refuses a submit
(P1) or an operations approval (P2) by the enterer.

### 3.4 Rules

1. An intake record is a record with a source key, a received time, an evidence file, or a channel other than empty
   and `Manual` (`card.intake.has_intake_provenance`). The channel `Manual` alone is a hand entry.
2. Intake never approves, submits or posts. This is the rule of `card/intake.py` today and stays.
3. The second-person rule is by company and off by default. Off means the behavior of today, without a warning.
4. The server reads the enterer from stored values (`owner`, `edited_by`). It never trusts a value from the browser.
5. Administrator is not exempt (same as the monthly card rule in `card.governance.before_submit`).
6. A reviewer can correct a value in the draft before he submits. The change history (`track_changes`) shows it.
   If he saves the draft before he submits, he becomes an enterer and cannot submit. See the limit in section 4.
7. The rule covers only records that the enterer marked as intake. A record marked one time stays marked: the
   server keeps the flag `intake_declared` when the intake fields are emptied later. Making the intake fields
   mandatory is a separate owner decision and is not proposed.

### 3.5 Permissions

No new role, DocPerm, share or endpoint in P1 to P6. The rule of P1 and P2 removes an action from one user in one
situation. It grants nothing. If a company has one manager who also types the records, the rule blocks him. For
this reason the rule is off by default and the owner turns it on for each company.

Company isolation stays as built: `has_transport_permission` (FR-072) and `has_diesel_fill_permission`.

### 3.6 File privacy

- Evidence is a private file of its own record. The transport enforces this with
  `card.attachment_validator.require_record_file` (URL under `/private/files/`, `is_private` = 1, attached to this
  record or the user's own new upload). Accepted content: JPEG, PNG, WebP or PDF, at most 10 MB
  (`check_attachment_content`, `MAX_BYTES`).
- Frappe behavior that every part must respect: files with identical content share one URL and one disk file. When
  one File row changes between private and public, Frappe changes all rows with that content. The docstrings of
  `card/custody_receipt.py` and of `card.intake.keep_transport_evidence_file` describe it. Any new evidence field
  (P4, P5) needs the same `before_validate` guard that also looks at rows with the same `content_hash`.
- Known limits stay as written in section 0 of the base design (raw deletes, `File.optimize_file` on a draft).
- No evidence leaves the server. No part sends a file or text to an external service.

### 3.7 Retention

No automatic deletion in any part. If the owner later sets a number of years (decision 3), the design is a report
that lists evidence older than the limit on draft or rejected records only. A person deletes the files. The File
guards continue to refuse deletion for submitted and cancelled records.

### 3.8 Migration

- P1: one new column on the settings child table and one on the transport, default 0. No patch. No backfill.
  A draft with intake provenance gets the flag at its next save. Submitted and cancelled transports do not
  change. A second `migrate` changes nothing.
- P3: two new empty columns. No patch.
- P4: hooks only. Existing files are protected from the first request after the deploy. No data change.
- P5 and P7: a new table each. Empty at install. Diesel `source_key` migration stays as base design section 8.
- Rollback for every part: revert the code. The new columns stay in the database with their values and have no effect.

### 3.9 Tests for every part

- Setting off: the full existing suites pass without change (`test_transport_intake.py`, `test_card_day_intake.py`,
  `test_diesel_session_evidence.py`, `test_diesel_import.py`).
- Allowed and refused users, with Administrator as a refused user.
- Two companies: the setting of company A never affects a record of company B.
- Desk save, REST and `frappe.client.submit` give the same result.
- File tests for P4 and P5: delete, detach, make public, and a second file with the same content.
- Fresh install, upgrade and second migrate for each schema change.

## 4. Smallest safe slice

One change: **P1, the second-person rule for transports entered from evidence.**

**Built as FR-189 (In review, not merged, not released, not deployed).** Code: `card.intake.check_second_person`,
called first in `EquipmentTransport.before_submit`. Tests: `TestTransportIntakeSecondPerson` in
`card/tests/test_transport_intake.py`. The tests were not run on a bench in the build session. They must pass in
CI before a merge. The table and the lists below describe the slice as built.

| Item | Value |
|---|---|
| Setting | `Card Company Settings.require_intake_second_person` (Check), label "Transport from evidence needs a second person" |
| Default | 0 (off). A company without a settings row is also off (`card.settings.company_setting` returns `None`) |
| Behavior when off | Exactly as today. No check, no message, no new stored value |
| Behavior when on | At submit of an Equipment Transport that is an intake record (rule 1 of section 3.4), the server refuses the submit when the session user is the stored `owner` or is in the stored `edited_by` list. The message tells him that another user must submit. A transport without intake fields is not affected |
| Read of the enterer | From the database row, not from the document in memory. `EquipmentTransport.validate` runs before `before_submit` and `_record_editor` adds the submitter to `edited_by` in memory |
| Delegation | Not part of the slice as built. A delegate (FR-163) of the enterer is a different user and can submit. To count the delegator as an enterer, as monthly cards do (`card.governance.user_acting_on_behalf`), is a later change |
| Forged request | The stored company and the stored intake fields count with the values sent. A submit request that changes the company, removes the provenance or names another `owner` or `edited_by` is refused also |
| New permission | None |
| New field on the transport | `intake_declared` (Check, default 0, hidden, read only, `no_copy`). `card.intake._set_intake_declared` writes it in `validate`: stored flag, or the flag of the amended transport, or intake provenance in this save. The request never decides it and it never returns to 0. The flag is recorded also with the setting off. `submitted_by` already records the reviewer |

Files to touch:

1. `card/card/doctype/card_company_settings/card_company_settings.json`: the Check field, `permlevel` 1 as the
   other company settings.
2. `card/intake.py`: `check_second_person`, `has_intake_provenance`, `_set_intake_declared`.
3. `card/card/doctype/equipment_transport/equipment_transport.py`: one call in `before_submit`.
4. `card/tests/test_transport_intake.py`: new tests (below).
5. `card/locale/`: the label and the message (Card strings only).
6. `CHANGELOG.md`, `docs/governance/FEATURE-REGISTRY.md` (new FR row), `docs/governance/SETTINGS-AND-CONSTANTS.md`,
   the two "What's new" pages and the generated Reference pages of the documentation site.

Tests:

1. Setting off: enterer submits his intake transport. Result: allowed, as today.
2. Setting on: enterer submits. Result: refused. A second manager submits. Result: allowed.
3. Setting on: a user who saved the draft one time (in `edited_by`) submits. Result: refused.
4. Setting on: transport without intake fields, submitted by its enterer. Result: allowed.
5. Setting on for company A only: an intake transport of company B is submitted by its enterer. Result: allowed.
6. Setting on: Administrator is the enterer and submits. Result: refused.
7. Setting on: insert as submitted in one call. Result: refused.
8. Setting on: a forged `owner` or `edited_by`, or the provenance removed in the submit request. Result: refused.
9. The same results through REST PUT with `docstatus` 1 and `frappe.client.submit`.
10. Setting on: the enterer empties the intake fields in a draft save, then submits. Result: refused.
11. A forged `intake_declared` in a save, through `set_value` or in the submit request. Result: ignored.
12. Setting on: an amendment built without the intake fields. Result: its enterer is refused.
13. Setting off: the flag is recorded and nothing is refused.

Not covered by a test: bulk submit and a workflow action (both call the same submit), and a delegate.

Known limit: a reviewer who changes values and submits in one request is not an enterer in the stored row, so the
submit is allowed. The change history shows his changes. This is accepted for the slice.

Effort estimate: about 2 working days. One day for code and tests, one day for the review gates, documentation and
a check on the existing Card QA site. No Production step is part of the slice.

No owner decision blocks the slice, because the setting is off for every company after a deploy. A merge, a
release, a deploy and turning the setting on for a company each need their own owner approval.

## 5. Open owner decisions

1. **Reopen #52 for the slice of section 4?** Decided 2026-11-25: yes, the slice only (owner instruction quoted at
   the top). Still open: the `deferred` label on the issue and the roadmap row.
2. **Which companies turn the second-person rule on, and when?** Options: (a) none now, (b) a named company after
   the release. Recommendation: (a) until two people handle transports in that company each day.
3. **How many years is evidence kept before a manual clean-up is allowed?** Options: (a) keep without limit,
   (b) a number of years that the accountant confirms. Recommendation: (a) now. No automatic deletion in both cases.
4. **Who types records from evidence?** Options: (a) office users only, as today, (b) operators also, from the
   phone. Recommendation: (a). Option (b) is a new permission and a new upload screen.
5. **What comes after the slice?** Options: (a) the same rule for diesel fills (P2), (b) sheet evidence on monthly
   cards (P5), (c) stop. Recommendation: (a), then (b).

## 6. Out of scope

- OCR and every other automatic reading of a photo or a sheet. If the owner approves one later, it runs on the
  company server, it is off by default, and it only proposes values for a person to accept.
- A link to the WhatsApp API or to any WhatsApp integration app. Card depends on `frappe` and `erpnext` only.
- Any external AI, OCR, storage or messaging service. No company data leaves the server without a separate owner
  approval.
- The `Card Intake Record` register and the adapter endpoint (P7), until an adapter is approved.
- Upload from Card Mobile.
- Changes to existing permissions, to accounting documents, or to data on a live site.
- Correction of the registry rows listed in section 1.4.
