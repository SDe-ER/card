# Intake provenance for movement and operation records — design

**Status: design; the Equipment Transport part is built as FR-146 (section 0).** Issue #52, work package WP-21. No code, DocType, permission or data change
comes with this file. Building any part of it needs the owner's GO, its own branch, tests, CHANGELOG entry and
FEATURE-REGISTRY row.

Baseline: `main` @ `1b7c20d` (v4.5.0).

## 0. As built for Equipment Transport (FR-146, WP-N1)

WP-N1 implements the transport part without the `Card Intake` register of section 3. It differs from this design
as follows; WP-N3 (`card.intake.propose`) and WP-N2 reuse these fields instead of adding new ones:

| Design | N1 as built |
|---|---|
| `card_intake` link and fetched `intake_channel`, server-written only (section 3.3) | Fields on the transport itself: `intake_channel`, `intake_source_key`, `intake_received_on`, `intake_evidence`, `intake_evidence_hash`. All optional, empty by default, `no_copy`; editable by the user on a draft (there is no adapter yet), frozen after submit. Only `intake_evidence_hash` is server-written (SHA-256 of the private evidence file; a client value is never kept) |
| Unique index on (`company`, `source_key`) (section 4) | No database unique index: one live (draft or submitted) transport per company and key, checked in `validate` under a lock on the Company row plus a locking read (`frappe.qb ... .for_update()`); a cancelled transport frees its key, so its amendment keeps it |
| Canonical `source_key` = SHA-256 of channel + company + identity | The key is the external id as entered (stripped). Keys match case-insensitively (the column uses the database's case-insensitive collation: `WA-1` and `wa-1` are the same key) |
| Reused evidence refused (section 4) | Reused evidence on another live transport of the same company only warns (owner rule 2026-11-10: new rules are warn-only or opt-in) |
| `received_by` | The "operator" of #52 is the transport's `owner` plus `edited_by` (every user who saved the draft, kept by `_record_editor`) |

The evidence file of a submitted or cancelled transport cannot be deleted (`card.intake.keep_transport_evidence`,
File `on_trash`, also after it is detached), moved, detached, made public or renamed
(`card.intake.keep_transport_evidence_file`, File `before_validate`), and no intake field of a submitted transport
changes, also with an allow-on-submit customisation (`card.intake.freeze_submitted_intake`); a cancel that changes
them is refused by FR-123 (`card.cancel_reason._refuse_changes`).

## 1. Problem

Field data reaches the office on paper, in WhatsApp messages and photos, and from external systems. Today only
diesel fills keep where they came from (FR-085, FR-086, FR-086b). Equipment movements (Equipment Transport) and
operation records (Card Monthly Card days) are typed in by hand with no link to the original message or sheet, no
duplicate protection across re-entry, and no review record of who checked the source.

Goal (#52): every movement and operation record created from an outside source keeps the original evidence, the
channel, the time it was received and the person who entered it; the same source can never create two records; and
an imported record goes through the same validation and approval as a hand-entered one.

## 2. What exists for diesel (the pattern to generalise)

| Element | Where | Behaviour |
|---|---|---|
| Source key | `project_diesel_fill.json` `source_key` (Data, unique, read only) | One fill per session; a re-run finds the existing fill in any state and skips it (`diesel_import.py:65-68`) |
| Source text | `source_messages`, `source_caption` (read only) | Original messages plus the original photo hashes (`diesel_import.py:158-165`) |
| Evidence files | `opening_photo`, `closing_photo`, private `File` rows attached to the fill (`diesel_import.py:212-224`) | SHA-256 of each photo checked against the manifest before anything is written (`diesel_import.py:101-113`) |
| Duplicate evidence | `_check_unused` (`diesel_import.py:192-210`) and the fill's own photo check | One photo proves one live fill; a rejected or cancelled fill frees it |
| Forgery guard | `project_diesel_fill.py:151-160` `SOURCE_FIELDS`, `:326-341` `_guard_source` | Source fields are written by the import only (`doc.flags.diesel_import`); a Desk or REST save cannot set or change them; an amendment keeps the source but not the unique key |
| Same validation | `diesel_import.py:74` `doc.insert()` | The fill's own `validate` runs; nothing is approved, submitted or posted |
| Entry point | `import_sessions` via `bench execute` (`diesel_import.py:35-54`) | Card Manager / System Manager and create permission; dry run by default; one savepoint per session |
| Review | `review_status` (Draft / Operations Approved / Rejected), permlevel 1, required before submit (FR-085) | Operations review on the fill itself |

Limits of the diesel pattern: the key is unique on one DocType only; provenance fields are copied onto the target,
so a second target type would repeat them; an external photo hash and the stored hash can differ (EXIF stripping,
`diesel_import.py:180-190`); there is no record of a source that was received but not yet turned into a fill.

## 3. Proposed data model

Two parts: a provenance register that every channel writes to, and a small set of read-only link fields on each
target DocType.

### 3.1 `Card Intake` (new, non-submittable, `track_changes` on)

One row per received source item (one paper sheet, one WhatsApp session, one external record).

| Field | Type | Notes |
|---|---|---|
| `company` | Link Company, required | Every check is company-scoped |
| `channel` | Select: Paper, WhatsApp, External, Desk | Fixed list; English stored values |
| `source_key` | Data, required, read only | SHA-256 hex of the canonical source identity (section 4). Unique together with `company` |
| `target_doctype` | Select: Equipment Transport, Card Monthly Card, Project Diesel Fill | Diesel is added later, when the existing fields are migrated (section 8) |
| `target_name` | Dynamic Link, read only | Set when a draft target is created |
| `received_on` | Datetime, required | When CARD received the source (not the event date) |
| `event_date` | Date | Date the source reports |
| `received_by` | Link User, read only | Session user of the import or the Desk entry |
| `external_reference` | Data | Message ids, sheet number, external system id (no phone numbers or names in public fixtures) |
| `source_text` | Small Text, read only | Original text as received |
| `status` | Select: Received, Needs Review, Draft Created, Rejected, Duplicate | Section 5 |
| `review_note` | Small Text | Required on Rejected |
| `reviewed_by`, `reviewed_on` | Link User, Datetime, read only, permlevel 1 | Set by the server |
| `evidence` | Table `Card Intake Evidence` | Section 3.2 |

### 3.2 `Card Intake Evidence` (child table)

| Field | Type | Notes |
|---|---|---|
| `file` | Attach, private | Always `is_private = 1` |
| `original_sha256` | Data, read only | Hash of the bytes as received |
| `stored_hash` | Data, read only | `File.content_hash` after upload (may differ from the original after EXIF stripping) |
| `role` | Select: Sheet, Photo, Message export, Other | |
| `captured_on` | Datetime | From the source when known |

### 3.3 Fields on each target DocType

`Equipment Transport` and `Card Monthly Card` get `card_intake` (Link Card Intake, read only, `no_copy`) and
`intake_channel` (fetched, read only). A server guard like `_guard_source` refuses any change to them outside the
intake service. For a monthly card, one intake can feed several day rows; the card day row gets an optional
`card_intake` link so each day keeps its own source.

## 4. Idempotency

- `source_key = sha256(channel + "\n" + company + "\n" + canonical identity)`, where the canonical identity is:
  - WhatsApp: the sorted message ids of the session, or, when ids are missing, the sorted original SHA-256 of its
    photos plus the sender's first message time;
  - Paper: the SHA-256 of the scanned sheet plus the sheet number;
  - External: system name plus the record id;
  - Desk: none (a hand entry without a source creates no intake).
- A unique index on (`company`, `source_key`) makes a second insert fail at the database. The service first reads
  the existing row and returns it as `Existing`, as `diesel_import` does today.
- Evidence reuse: an `original_sha256` or `stored_hash` already used by a live intake (status not Rejected) of the
  same company is refused, with the existing intake named. This generalises the diesel photo rule.
- A batch runs one savepoint per intake. A failed intake rolls back its rows and removes the files it wrote (same
  as `diesel_import._remove_files`).
- Re-running the same batch is safe; a dry run is the default.

## 5. Review flow

```
Received --(adapter parsed, checks passed)--> Needs Review --(reviewer accepts)--> Draft Created
    |                                              |
    +--(same source_key)--> Duplicate               +--(reviewer rejects, note required)--> Rejected
```

1. **Received.** The adapter stores the source and its evidence. Nothing else is created.
2. **Needs Review.** Parsed values are shown next to the evidence. Equipment and projects stay as reported text
   until matched (as diesel keeps `reported_name`, `match_status = Unmatched`); CARD never guesses a match.
3. **Draft Created.** On acceptance the service creates the target as a draft through `frappe.new_doc` and
   `insert()`, so the target's own validation applies (assignment rules `transfer.py:550` `validate_card_days`,
   duplicate card guard `card_monthly_card.py:315-334`, transport company isolation FR-072, period lock FR-050).
   A validation error leaves the intake in Needs Review with the message.
4. The target is approved and submitted by the normal path. Intake never submits, approves or posts.
5. **Rejected** frees the evidence for another intake. Cancelling a target created from an intake sets the intake
   back to Needs Review; the intake row is never deleted.

Separation of duties: the user who accepts an intake must not be the user who received it, when the owner
enables this (proposed Card Settings check, default off until decided, in line with FR-006).

## 6. Permissions

- New role rights: Card Manager and System Manager create, read and review intakes; Card Supervisor reads the
  intakes of his companies; Card User and Card Operator have no access. No existing role is widened.
- Company isolation: `has_permission` and `permission_query_conditions` hooks for `Card Intake`, the same rule as
  FR-070 to FR-072 (Company User Permissions apply; cross-company access denied on the server).
- Entry points: phase 1 is `bench execute` only, like `diesel_import.import_sessions`. A later Desk upload uses
  whitelisted methods with `methods=["POST"]`, an explicit `frappe.has_permission` check and the company check.
  No guest endpoint. No `ignore_permissions`.
- Files are private and attached to the intake. A reader of the target sees the evidence only with read rights on
  the intake.
- Field levels: review fields at permlevel 1; source fields read only and server-written.

## 7. Channels

| Channel | Phase 1 | Later |
|---|---|---|
| Paper | Manifest plus scanned sheets, `bench execute` | Desk upload form |
| WhatsApp | Exported, reviewed sessions plus photos (as diesel today) | The WhatsApp integration on the site, only after an owner decision; CARD itself depends on `frappe` and `erpnext` only |
| External | JSON manifest | REST adapter with an API user per system |

No cloud AI is required. Any automatic reading of a photo (for example a local meter-reading worker, PR #164) only
suggests values for review; it never sets a reviewed value.

## 8. Migration of the diesel fields

Diesel keeps its current fields until a separate approved change. That change would create one `Card Intake` per
fill that has a `source_key`, link it, and keep the old fields read only (no deletion). The existing unique index on
`Project Diesel Fill.source_key` stays until then.

## 9. Tests required before any merge

- Same source twice (and in parallel) creates one intake.
- Evidence reused across intakes and across companies.
- Source fields refused through Desk, REST and `frappe.client.set_value`.
- A target created from an intake fails the same validations as a hand-entered one.
- Company isolation for list, read, link search and review.
- Dry run writes no row and no file; a failed intake leaves no file on disk.

## 10. Open owner decisions

1. Which channels and target types come first (proposal: WhatsApp transports, then paper operation sheets).
2. Whether the receiver may also accept the intake.
3. Whether a monthly card takes one intake per day or per sheet.
4. Retention period of evidence files.
