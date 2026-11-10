# Domain map

Sources: `card/card/doctype/*/*.json`, their controllers, `card/hooks.py`, `card/gl/`, `card/transfer.py`,
`card/materials.py`, `card/modules.txt`. CARD is one Frappe app (`required_apps = ["erpnext"]`, `card/hooks.py`). It
does not depend on HRMS (`AGENTS.md`).

## 1. Bounded areas

```
 MASTER DATA          PLACEMENT            OPERATION             MONEY (drafts only)        STOCK / PARTS
 -------------        -----------          ---------------       -------------------        --------------------
 Card Equipment  -->  Equipment      -->   Card Monthly Card -->  GL Posting Log      -->    Equipment Needs Request
 Make/Model/Type/     Transport            Project Diesel Fill    (audit + reservation)       Equipment Needs Review
 Category             (submit moves        (+ Diesel Fill         builds a DRAFT              -> Material Request (draft)
 Party registries     equipment)           Equipment child)       Purchase Invoice or         Employee Tool Custody
 Card Settings        Card Equipment       Equipment Transport    Sales Invoice               -> Stock Entry
 (company rows)       Assignment                                                              Card Equipment Part
                      (derived location)                                                      (fitment, review)
```

## 2. DocTypes by area

Column "Kind" is read from the JSON: **Submittable**, **Master**, **Child**, **Single**. Naming is the `autoname`
value.

| Area | DocType | Kind | Naming | Links to (ERPNext or CARD) |
|---|---|---|---|---|
| Master data | Card Equipment | Master, track_changes | `CEQ-{####}` | Company, Asset, Project (current), Employee (operator), Supplier, Customer, Cost Center, Card Equipment Make/Model/Type/Category |
| Master data | Card Equipment Make, Model, Type, Category | Master | `CMK-`, `CEM-`, field name | Type links Asset Category |
| Master data | Card Equipment Component | Child of Card Equipment | none | Card Equipment (a unit and its pieces) |
| Master data | Card Equipment Supplier, Card Equipment Customer | Master (party registry, field name) | `field:supplier` / `field:customer` | Supplier / Customer. Registry rows hold the party only; figures are computed per company on read, no longer stored (patch `v1_2_2.clear_registry_aggregates`); `card/party_registry.py` keeps names in step on rename |
| Settings | Card Settings | Single, track_changes | none | Role, Warehouse, Supplier; child tables below |
| Settings | Card Company Settings | Child of Card Settings (one row per company) | none | Company, Account, Cost Center, Item, Item Tax Template, tax templates, Mode of Payment, Location |
| Settings | Card Adjustment Type, Card Diesel Price, Card Project Transport Price, Card Location Cost Center | Children of Card Settings | none | Company, Account, Item, Currency, UOM, Project, Location, Cost Center |
| Placement | Card Equipment Assignment | Master, track_changes (not submittable) | `CEA-{####}` | Card Equipment, Project, Cost Center |
| Placement | Equipment Transport | Submittable, track_changes | `TRN-.#####` | Project (destination, source, cost, billing), Supplier (transporter, equipment supplier), Customer, Location, Cost Center, Purchase Invoice, GL Posting Log, Card Equipment Assignment |
| Placement | Equipment Transport Item | Child of Equipment Transport | none | Card Equipment, previous/created assignment, Project, Location |
| Operation | Card Monthly Card | Submittable, track_changes | `EOMC-{year}-{month}-{####}` | Card Equipment, Project, Company, Supplier, Customer, Employee, Purchase Invoice, Sales Invoice, GL Posting Log |
| Operation | Card Monthly Card Day, Card Monthly Card Adjustment | Children of Card Monthly Card | none | none (day status, hours; typed additions and deductions with a side) |
| Operation | Project Diesel Fill | Submittable, track_changes | `DSL-.#####` | Project, Supplier, Company, Card Equipment, Cost Center, Purchase Invoice, GL Posting Log |
| Operation | Diesel Fill Equipment | Child of Project Diesel Fill | none | Card Equipment (match status Unmatched, Matched, Third Party) |
| Money | GL Posting Log | Audit record, no user edits | none | Company, Supplier or Customer, Purchase Invoice / Sales Invoice / Journal Entry (dynamic), User |
| Money | GL Posting Source | Child of GL Posting Log | none | Card Monthly Card / Project Diesel Fill / Equipment Transport (dynamic) |
| Stock and parts | Equipment Needs Request | Submittable, track_changes | `ENR-.#####` | Card Equipment, Project, Employee, User |
| Stock and parts | Equipment Needs Review | Submittable, track_changes | `ENV-.#####` | Project, User; lines link Material Request and Employee Tool Custody |
| Stock and parts | Employee Tool Custody | Submittable, track_changes | `ETC-.#####` | Employee, Item, Warehouse, Project, Card Equipment, Stock Entry |
| Stock and parts | Card Equipment Part | Master, track_changes (fitment: which part fits which model or machine) | `CFP-{#####}` | Item, Card Equipment Model, Card Equipment, User, Equipment Needs Request, Company |

Workspace, number cards, dashboard charts, print formats and roles `Card Manager` / `Card User` ship as fixtures
(`card/hooks.py` `fixtures`). Other roles used by the code (`Card Supervisor`, `Card Operator`, `Accounts Manager`,
`Stock Manager`) are read from the DocType permissions; the full role-by-action table is in
[ROLE-ACTION-MATRIX.md](../governance/ROLE-ACTION-MATRIX.md).

## 3. Hooks that tie CARD to ERPNext

From `card/hooks.py`:

| Hook | Target | Handler | Purpose |
|---|---|---|---|
| `doc_events` | Card Monthly Card, Project Diesel Fill, Equipment Transport | `card.period_lock.on_validate / on_cancel / on_trash` | Server-side period lock. An override by the configured role is logged, notified and, since FR-123 (#197), also written as a Comment on the document |
| `doc_events` | the same three | `card.cancel_reason.on_validate` (validate), `before_update_after_submit`, `before_cancel`, `on_cancel` | FR-123 (#197): a cancel needs a reason, changes no other stored field or row, and leaves a Comment with actor, reason and date. A save never keeps a reason. The form's Cancel button is replaced by `card.cancel_reason.cancel_with_reason` (`card/public/js/cancel_reason.js`) |
| `doc_events` | the same three | `card.gl.events.block_source_cancel` (before_cancel, runs after the cancel-reason check) | A source held by an active posting cannot be cancelled |
| `doc_events` | Purchase Invoice, Sales Invoice | `card.gl.events.validate / before_submit / on_submit / before_cancel / on_trash` | Keeps the posting log and the source links true; blocks edits that would break the build |
| `doc_events` | Journal Entry | `card.gl.journal_link.before_cancel` | Frees cards when a linked accrual is cancelled |
| `doc_events` | Supplier, Customer | `card.party_registry.before_rename / after_rename` | Keeps the party registries in step |
| `doc_events` | Version, DocShare, File, Property Setter | field masking, cross-company share denial, private custody receipts, registry history guard | Privacy and isolation |
| `permission_query_conditions` and `has_permission` | party registries, Needs Request, Assignment, Fitment part, Monthly Card, Transport, Diesel Fill, Tool Custody | company scoping | Cross-company reads and writes refused on the server |
| `scheduler_events` daily | Card Equipment | `card.transfer.sync_equipment_locations_daily` | Daily location sync, runs only when Card Settings enables it (`card/transfer.py` module docstring) |
| `override_doctype_dashboards` | Supplier, Asset, Project, Customer | `card.dashboards.*` | Connections tab entries only |

CARD adds no `override_doctype_class`. It adds one Accounting Dimension, "Card Equipment" (`card/dimension.py`), created
only by an explicit manual command, never by migrate.

## 4. Where CARD stops and ERPNext starts

| CARD owns | ERPNext owns |
|---|---|
| Which machine, where, on which dates (Equipment, Assignment, Transport) | Project, Cost Center, Location, Asset, Item masters |
| What the machine did and what it is worth in a month (Monthly Card, Diesel Fill) | Purchase Invoice, Sales Invoice, Payment Entry, Journal Entry, GL Entry, VAT |
| Reservation and audit of what was invoiced (GL Posting Log) | Stock Entry, Material Request, stock ledger |
| Review and approval of needs, fitment and custody | Employee, Supplier, Customer masters |

CARD creates standard documents through the Document API and links back to them (details in
[05-accounting-examples.md](05-accounting-examples.md)). It never inserts a GL Entry (`AGENTS.md`).

## 5. Not in the code (Planned)

| Concept in #40 | State | Issue |
|---|---|---|
| Project contract with multiple customers and a commercial responsibility matrix | No contract DocType. A customer is carried on the equipment and the card | #41 |
| Configurable stopped reasons with no automatic entitlement | Only a fixed day-status Select (work, day off, holiday, client stop) | #45 |
| Tank inventory and bulk fuel delivery allocation | No tank or delivery DocType. Diesel stays per-fill | #47 |
| Maintenance and operating-cost capture by equipment | Reports read ERPNext expenses; no capture DocType | #48 |
| Period approval before billing | No period document. Posting is by party and month | #49 |
| Paper and WhatsApp intake for transports and cards | Only diesel fills keep provenance | #52 |
| Profitability and cost provenance reporting | Partial reports exist (`equipment_partial_margin`, `operating_cost_by_project`) | #53 |
