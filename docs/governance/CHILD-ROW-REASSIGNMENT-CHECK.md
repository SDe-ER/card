# FR-153 child row reassignment: read-only detection check

**Status:** In review (FR-153, SEC-2). This page is documentation. It is not a patch, it is not run by `bench migrate`,
and it writes nothing.

## Why

Before FR-153, a save of a CARD document could carry the name of a stored row of **another** document. Frappe then
moved that row to the saved document (`frappe/model/document.py` `update_child_table` / `db_update`). The other
document was not saved, so its own checks did not run: it could stay submitted or approved and lose rows. FR-153
(`card/child_integrity.py`) refuses this from now on. It does not repair or detect rows moved before it was
installed. The queries below help the owner look for such rows. They list **candidates to review**, not proven
cases: patches, imports and older code can produce the same signs.

## How to run (read only)

Run on a backup copy first if possible. On the site's database console (`bench --site <site> mariadb`), start a
read-only transaction, run the queries, then end the transaction:

```sql
SET SESSION TRANSACTION READ ONLY;
START TRANSACTION READ ONLY;
-- the queries below (SELECT only)
ROLLBACK;
```

Every statement is a `SELECT`. None of them changes data. The DocType and table list was taken from the CARD
DocType JSON files of this commit (the same list `card.child_integrity.card_doctypes()` returns). A newer CARD
version may add tables; regenerate the list then.

## Check 1 — submitted documents with an empty table

A stolen row leaves its submitted document with fewer rows. A document whose table is empty is the clearest sign.
Some tables may be empty by design (for example agreement responsibilities); review each hit against the document's
Version history (the rows listed at submit).

```sql
SELECT 'Card Daily Log' AS doctype, p.name, p.docstatus, p.modified, 'rows' AS table_field
FROM `tabCard Daily Log` p
WHERE p.docstatus = 1
  AND NOT EXISTS (SELECT 1 FROM `tabCard Daily Log Row` c WHERE c.parent = p.name AND c.parenttype = 'Card Daily Log' AND c.parentfield = 'rows')
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name, p.docstatus, p.modified, 'days' AS table_field
FROM `tabCard Monthly Card` p
WHERE p.docstatus = 1
  AND NOT EXISTS (SELECT 1 FROM `tabCard Monthly Card Day` c WHERE c.parent = p.name AND c.parenttype = 'Card Monthly Card' AND c.parentfield = 'days')
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name, p.docstatus, p.modified, 'adjustments' AS table_field
FROM `tabCard Monthly Card` p
WHERE p.docstatus = 1
  AND NOT EXISTS (SELECT 1 FROM `tabCard Monthly Card Adjustment` c WHERE c.parent = p.name AND c.parenttype = 'Card Monthly Card' AND c.parentfield = 'adjustments')
UNION ALL
SELECT 'Card Period Run' AS doctype, p.name, p.docstatus, p.modified, 'sources' AS table_field
FROM `tabCard Period Run` p
WHERE p.docstatus = 1
  AND NOT EXISTS (SELECT 1 FROM `tabCard Period Run Source` c WHERE c.parent = p.name AND c.parenttype = 'Card Period Run' AND c.parentfield = 'sources')
UNION ALL
SELECT 'Card Rate Agreement' AS doctype, p.name, p.docstatus, p.modified, 'responsibilities' AS table_field
FROM `tabCard Rate Agreement` p
WHERE p.docstatus = 1
  AND NOT EXISTS (SELECT 1 FROM `tabCard Agreement Responsibility` c WHERE c.parent = p.name AND c.parenttype = 'Card Rate Agreement' AND c.parentfield = 'responsibilities')
UNION ALL
SELECT 'Equipment Needs Request' AS doctype, p.name, p.docstatus, p.modified, 'items' AS table_field
FROM `tabEquipment Needs Request` p
WHERE p.docstatus = 1
  AND NOT EXISTS (SELECT 1 FROM `tabEquipment Needs Request Item` c WHERE c.parent = p.name AND c.parenttype = 'Equipment Needs Request' AND c.parentfield = 'items')
UNION ALL
SELECT 'Equipment Needs Review' AS doctype, p.name, p.docstatus, p.modified, 'items' AS table_field
FROM `tabEquipment Needs Review` p
WHERE p.docstatus = 1
  AND NOT EXISTS (SELECT 1 FROM `tabEquipment Needs Review Item` c WHERE c.parent = p.name AND c.parenttype = 'Equipment Needs Review' AND c.parentfield = 'items')
UNION ALL
SELECT 'Equipment Transport' AS doctype, p.name, p.docstatus, p.modified, 'items' AS table_field
FROM `tabEquipment Transport` p
WHERE p.docstatus = 1
  AND NOT EXISTS (SELECT 1 FROM `tabEquipment Transport Item` c WHERE c.parent = p.name AND c.parenttype = 'Equipment Transport' AND c.parentfield = 'items')
UNION ALL
SELECT 'Project Diesel Fill' AS doctype, p.name, p.docstatus, p.modified, 'equipment_filled' AS table_field
FROM `tabProject Diesel Fill` p
WHERE p.docstatus = 1
  AND NOT EXISTS (SELECT 1 FROM `tabDiesel Fill Equipment` c WHERE c.parent = p.name AND c.parenttype = 'Project Diesel Fill' AND c.parentfield = 'equipment_filled')
ORDER BY 1, 2;
```

## Check 1b — submitted documents with a gap in their row numbers

Frappe numbers the rows of a document 1, 2, 3 ... (`idx`) and a submitted document cannot remove rows. A row taken
from a submitted or cancelled document leaves a gap (for example rows 1 and 3 only), and the receiving document can
hold two rows with the same number when the request did not renumber them. Each hit is a candidate.

```sql
SELECT 'Card Daily Log' AS doctype, p.name, p.docstatus, 'rows' AS table_field, COUNT(c.name) AS row_count,
  MIN(c.idx) AS min_idx, MAX(c.idx) AS max_idx, COUNT(DISTINCT c.idx) AS distinct_idx
FROM `tabCard Daily Log` p JOIN `tabCard Daily Log Row` c ON c.parent = p.name AND c.parenttype = 'Card Daily Log' AND c.parentfield = 'rows'
WHERE p.docstatus IN (1, 2)
GROUP BY p.name, p.docstatus
HAVING MIN(c.idx) <> 1 OR MAX(c.idx) <> COUNT(c.name) OR COUNT(DISTINCT c.idx) <> COUNT(c.name)
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name, p.docstatus, 'days' AS table_field, COUNT(c.name) AS row_count,
  MIN(c.idx) AS min_idx, MAX(c.idx) AS max_idx, COUNT(DISTINCT c.idx) AS distinct_idx
FROM `tabCard Monthly Card` p JOIN `tabCard Monthly Card Day` c ON c.parent = p.name AND c.parenttype = 'Card Monthly Card' AND c.parentfield = 'days'
WHERE p.docstatus IN (1, 2)
GROUP BY p.name, p.docstatus
HAVING MIN(c.idx) <> 1 OR MAX(c.idx) <> COUNT(c.name) OR COUNT(DISTINCT c.idx) <> COUNT(c.name)
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name, p.docstatus, 'adjustments' AS table_field, COUNT(c.name) AS row_count,
  MIN(c.idx) AS min_idx, MAX(c.idx) AS max_idx, COUNT(DISTINCT c.idx) AS distinct_idx
FROM `tabCard Monthly Card` p JOIN `tabCard Monthly Card Adjustment` c ON c.parent = p.name AND c.parenttype = 'Card Monthly Card' AND c.parentfield = 'adjustments'
WHERE p.docstatus IN (1, 2)
GROUP BY p.name, p.docstatus
HAVING MIN(c.idx) <> 1 OR MAX(c.idx) <> COUNT(c.name) OR COUNT(DISTINCT c.idx) <> COUNT(c.name)
UNION ALL
SELECT 'Card Period Run' AS doctype, p.name, p.docstatus, 'sources' AS table_field, COUNT(c.name) AS row_count,
  MIN(c.idx) AS min_idx, MAX(c.idx) AS max_idx, COUNT(DISTINCT c.idx) AS distinct_idx
FROM `tabCard Period Run` p JOIN `tabCard Period Run Source` c ON c.parent = p.name AND c.parenttype = 'Card Period Run' AND c.parentfield = 'sources'
WHERE p.docstatus IN (1, 2)
GROUP BY p.name, p.docstatus
HAVING MIN(c.idx) <> 1 OR MAX(c.idx) <> COUNT(c.name) OR COUNT(DISTINCT c.idx) <> COUNT(c.name)
UNION ALL
SELECT 'Card Rate Agreement' AS doctype, p.name, p.docstatus, 'responsibilities' AS table_field, COUNT(c.name) AS row_count,
  MIN(c.idx) AS min_idx, MAX(c.idx) AS max_idx, COUNT(DISTINCT c.idx) AS distinct_idx
FROM `tabCard Rate Agreement` p JOIN `tabCard Agreement Responsibility` c ON c.parent = p.name AND c.parenttype = 'Card Rate Agreement' AND c.parentfield = 'responsibilities'
WHERE p.docstatus IN (1, 2)
GROUP BY p.name, p.docstatus
HAVING MIN(c.idx) <> 1 OR MAX(c.idx) <> COUNT(c.name) OR COUNT(DISTINCT c.idx) <> COUNT(c.name)
UNION ALL
SELECT 'Equipment Needs Request' AS doctype, p.name, p.docstatus, 'items' AS table_field, COUNT(c.name) AS row_count,
  MIN(c.idx) AS min_idx, MAX(c.idx) AS max_idx, COUNT(DISTINCT c.idx) AS distinct_idx
FROM `tabEquipment Needs Request` p JOIN `tabEquipment Needs Request Item` c ON c.parent = p.name AND c.parenttype = 'Equipment Needs Request' AND c.parentfield = 'items'
WHERE p.docstatus IN (1, 2)
GROUP BY p.name, p.docstatus
HAVING MIN(c.idx) <> 1 OR MAX(c.idx) <> COUNT(c.name) OR COUNT(DISTINCT c.idx) <> COUNT(c.name)
UNION ALL
SELECT 'Equipment Needs Review' AS doctype, p.name, p.docstatus, 'items' AS table_field, COUNT(c.name) AS row_count,
  MIN(c.idx) AS min_idx, MAX(c.idx) AS max_idx, COUNT(DISTINCT c.idx) AS distinct_idx
FROM `tabEquipment Needs Review` p JOIN `tabEquipment Needs Review Item` c ON c.parent = p.name AND c.parenttype = 'Equipment Needs Review' AND c.parentfield = 'items'
WHERE p.docstatus IN (1, 2)
GROUP BY p.name, p.docstatus
HAVING MIN(c.idx) <> 1 OR MAX(c.idx) <> COUNT(c.name) OR COUNT(DISTINCT c.idx) <> COUNT(c.name)
UNION ALL
SELECT 'Equipment Transport' AS doctype, p.name, p.docstatus, 'items' AS table_field, COUNT(c.name) AS row_count,
  MIN(c.idx) AS min_idx, MAX(c.idx) AS max_idx, COUNT(DISTINCT c.idx) AS distinct_idx
FROM `tabEquipment Transport` p JOIN `tabEquipment Transport Item` c ON c.parent = p.name AND c.parenttype = 'Equipment Transport' AND c.parentfield = 'items'
WHERE p.docstatus IN (1, 2)
GROUP BY p.name, p.docstatus
HAVING MIN(c.idx) <> 1 OR MAX(c.idx) <> COUNT(c.name) OR COUNT(DISTINCT c.idx) <> COUNT(c.name)
UNION ALL
SELECT 'Project Diesel Fill' AS doctype, p.name, p.docstatus, 'equipment_filled' AS table_field, COUNT(c.name) AS row_count,
  MIN(c.idx) AS min_idx, MAX(c.idx) AS max_idx, COUNT(DISTINCT c.idx) AS distinct_idx
FROM `tabProject Diesel Fill` p JOIN `tabDiesel Fill Equipment` c ON c.parent = p.name AND c.parenttype = 'Project Diesel Fill' AND c.parentfield = 'equipment_filled'
WHERE p.docstatus IN (1, 2)
GROUP BY p.name, p.docstatus
HAVING MIN(c.idx) <> 1 OR MAX(c.idx) <> COUNT(c.name) OR COUNT(DISTINCT c.idx) <> COUNT(c.name)
ORDER BY 1, 2;
```

## Check 2 — rows created before their current document

A moved row keeps its own `creation` only when the request carried it (the Desk form sends the full row); otherwise
Frappe gives it the receiving document's `creation` and owner, and this check cannot see it. On normal data a row is
created with or after its document (amendments and `frappe.copy_doc` give new rows). A row older than its document
is a candidate. Card Settings is a Single and is left out.

```sql
SELECT 'Card Daily Log' AS doctype, p.name AS parent, 'Card Daily Log Row' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabCard Daily Log Row` c JOIN `tabCard Daily Log` p ON p.name = c.parent
WHERE c.parenttype = 'Card Daily Log' AND c.parentfield = 'rows'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Card Equipment' AS doctype, p.name AS parent, 'Card Equipment Component' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabCard Equipment Component` c JOIN `tabCard Equipment` p ON p.name = c.parent
WHERE c.parenttype = 'Card Equipment' AND c.parentfield = 'components'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Card Equipment' AS doctype, p.name AS parent, 'Card Consumption Rate' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabCard Consumption Rate` c JOIN `tabCard Equipment` p ON p.name = c.parent
WHERE c.parenttype = 'Card Equipment' AND c.parentfield = 'consumption_rates'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Card Equipment Type' AS doctype, p.name AS parent, 'Card Type Consumption Rate' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabCard Type Consumption Rate` c JOIN `tabCard Equipment Type` p ON p.name = c.parent
WHERE c.parenttype = 'Card Equipment Type' AND c.parentfield = 'default_consumption_rates'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name AS parent, 'Card Monthly Card Day' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabCard Monthly Card Day` c JOIN `tabCard Monthly Card` p ON p.name = c.parent
WHERE c.parenttype = 'Card Monthly Card' AND c.parentfield = 'days'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name AS parent, 'Card Monthly Card Adjustment' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabCard Monthly Card Adjustment` c JOIN `tabCard Monthly Card` p ON p.name = c.parent
WHERE c.parenttype = 'Card Monthly Card' AND c.parentfield = 'adjustments'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Card Period Run' AS doctype, p.name AS parent, 'Card Period Run Source' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabCard Period Run Source` c JOIN `tabCard Period Run` p ON p.name = c.parent
WHERE c.parenttype = 'Card Period Run' AND c.parentfield = 'sources'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Card Rate Agreement' AS doctype, p.name AS parent, 'Card Agreement Responsibility' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabCard Agreement Responsibility` c JOIN `tabCard Rate Agreement` p ON p.name = c.parent
WHERE c.parenttype = 'Card Rate Agreement' AND c.parentfield = 'responsibilities'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Equipment Needs Request' AS doctype, p.name AS parent, 'Equipment Needs Request Item' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabEquipment Needs Request Item` c JOIN `tabEquipment Needs Request` p ON p.name = c.parent
WHERE c.parenttype = 'Equipment Needs Request' AND c.parentfield = 'items'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Equipment Needs Review' AS doctype, p.name AS parent, 'Equipment Needs Review Item' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabEquipment Needs Review Item` c JOIN `tabEquipment Needs Review` p ON p.name = c.parent
WHERE c.parenttype = 'Equipment Needs Review' AND c.parentfield = 'items'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Equipment Transport' AS doctype, p.name AS parent, 'Equipment Transport Item' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabEquipment Transport Item` c JOIN `tabEquipment Transport` p ON p.name = c.parent
WHERE c.parenttype = 'Equipment Transport' AND c.parentfield = 'items'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'GL Posting Log' AS doctype, p.name AS parent, 'GL Posting Source' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabGL Posting Source` c JOIN `tabGL Posting Log` p ON p.name = c.parent
WHERE c.parenttype = 'GL Posting Log' AND c.parentfield = 'sources'
  AND c.creation < p.creation - INTERVAL 1 SECOND
UNION ALL
SELECT 'Project Diesel Fill' AS doctype, p.name AS parent, 'Diesel Fill Equipment' AS child_doctype, c.name AS row_name, c.creation AS row_created, p.creation AS parent_created
FROM `tabDiesel Fill Equipment` c JOIN `tabProject Diesel Fill` p ON p.name = c.parent
WHERE c.parenttype = 'Project Diesel Fill' AND c.parentfield = 'equipment_filled'
  AND c.creation < p.creation - INTERVAL 1 SECOND
ORDER BY 1, 2;
```

## Check 3 — rows whose `modified` differs from their document's

Frappe stamps every row with its document's `modified` when the document is saved. A row saved on its own (for
example through `frappe.client.bulk_update` of the child DocType, which does not save the document) keeps a
different stamp. CARD code that updates a single row field (`db_set`) can also cause this, so review the hits.

```sql
SELECT 'Card Daily Log' AS doctype, p.name AS parent, 'Card Daily Log Row' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabCard Daily Log Row` c JOIN `tabCard Daily Log` p ON p.name = c.parent
WHERE c.parenttype = 'Card Daily Log' AND c.parentfield = 'rows'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Card Equipment' AS doctype, p.name AS parent, 'Card Equipment Component' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabCard Equipment Component` c JOIN `tabCard Equipment` p ON p.name = c.parent
WHERE c.parenttype = 'Card Equipment' AND c.parentfield = 'components'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Card Equipment' AS doctype, p.name AS parent, 'Card Consumption Rate' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabCard Consumption Rate` c JOIN `tabCard Equipment` p ON p.name = c.parent
WHERE c.parenttype = 'Card Equipment' AND c.parentfield = 'consumption_rates'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Card Equipment Type' AS doctype, p.name AS parent, 'Card Type Consumption Rate' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabCard Type Consumption Rate` c JOIN `tabCard Equipment Type` p ON p.name = c.parent
WHERE c.parenttype = 'Card Equipment Type' AND c.parentfield = 'default_consumption_rates'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name AS parent, 'Card Monthly Card Day' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabCard Monthly Card Day` c JOIN `tabCard Monthly Card` p ON p.name = c.parent
WHERE c.parenttype = 'Card Monthly Card' AND c.parentfield = 'days'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name AS parent, 'Card Monthly Card Adjustment' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabCard Monthly Card Adjustment` c JOIN `tabCard Monthly Card` p ON p.name = c.parent
WHERE c.parenttype = 'Card Monthly Card' AND c.parentfield = 'adjustments'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Card Period Run' AS doctype, p.name AS parent, 'Card Period Run Source' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabCard Period Run Source` c JOIN `tabCard Period Run` p ON p.name = c.parent
WHERE c.parenttype = 'Card Period Run' AND c.parentfield = 'sources'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Card Rate Agreement' AS doctype, p.name AS parent, 'Card Agreement Responsibility' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabCard Agreement Responsibility` c JOIN `tabCard Rate Agreement` p ON p.name = c.parent
WHERE c.parenttype = 'Card Rate Agreement' AND c.parentfield = 'responsibilities'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Equipment Needs Request' AS doctype, p.name AS parent, 'Equipment Needs Request Item' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabEquipment Needs Request Item` c JOIN `tabEquipment Needs Request` p ON p.name = c.parent
WHERE c.parenttype = 'Equipment Needs Request' AND c.parentfield = 'items'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Equipment Needs Review' AS doctype, p.name AS parent, 'Equipment Needs Review Item' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabEquipment Needs Review Item` c JOIN `tabEquipment Needs Review` p ON p.name = c.parent
WHERE c.parenttype = 'Equipment Needs Review' AND c.parentfield = 'items'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Equipment Transport' AS doctype, p.name AS parent, 'Equipment Transport Item' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabEquipment Transport Item` c JOIN `tabEquipment Transport` p ON p.name = c.parent
WHERE c.parenttype = 'Equipment Transport' AND c.parentfield = 'items'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'GL Posting Log' AS doctype, p.name AS parent, 'GL Posting Source' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabGL Posting Source` c JOIN `tabGL Posting Log` p ON p.name = c.parent
WHERE c.parenttype = 'GL Posting Log' AND c.parentfield = 'sources'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
UNION ALL
SELECT 'Project Diesel Fill' AS doctype, p.name AS parent, 'Diesel Fill Equipment' AS child_doctype, c.name AS row_name, c.modified AS row_modified, p.modified AS parent_modified, p.docstatus
FROM `tabDiesel Fill Equipment` c JOIN `tabProject Diesel Fill` p ON p.name = c.parent
WHERE c.parenttype = 'Project Diesel Fill' AND c.parentfield = 'equipment_filled'
  AND ABS(TIMESTAMPDIFF(SECOND, c.modified, p.modified)) > 1
ORDER BY 1, 2;
```

## Check 4 — rows whose `docstatus` differs from their document's

```sql
SELECT 'Card Daily Log' AS doctype, p.name AS parent, 'Card Daily Log Row' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabCard Daily Log Row` c JOIN `tabCard Daily Log` p ON p.name = c.parent
WHERE c.parenttype = 'Card Daily Log' AND c.parentfield = 'rows'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Card Equipment' AS doctype, p.name AS parent, 'Card Equipment Component' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabCard Equipment Component` c JOIN `tabCard Equipment` p ON p.name = c.parent
WHERE c.parenttype = 'Card Equipment' AND c.parentfield = 'components'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Card Equipment' AS doctype, p.name AS parent, 'Card Consumption Rate' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabCard Consumption Rate` c JOIN `tabCard Equipment` p ON p.name = c.parent
WHERE c.parenttype = 'Card Equipment' AND c.parentfield = 'consumption_rates'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Card Equipment Type' AS doctype, p.name AS parent, 'Card Type Consumption Rate' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabCard Type Consumption Rate` c JOIN `tabCard Equipment Type` p ON p.name = c.parent
WHERE c.parenttype = 'Card Equipment Type' AND c.parentfield = 'default_consumption_rates'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name AS parent, 'Card Monthly Card Day' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabCard Monthly Card Day` c JOIN `tabCard Monthly Card` p ON p.name = c.parent
WHERE c.parenttype = 'Card Monthly Card' AND c.parentfield = 'days'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Card Monthly Card' AS doctype, p.name AS parent, 'Card Monthly Card Adjustment' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabCard Monthly Card Adjustment` c JOIN `tabCard Monthly Card` p ON p.name = c.parent
WHERE c.parenttype = 'Card Monthly Card' AND c.parentfield = 'adjustments'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Card Period Run' AS doctype, p.name AS parent, 'Card Period Run Source' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabCard Period Run Source` c JOIN `tabCard Period Run` p ON p.name = c.parent
WHERE c.parenttype = 'Card Period Run' AND c.parentfield = 'sources'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Card Rate Agreement' AS doctype, p.name AS parent, 'Card Agreement Responsibility' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabCard Agreement Responsibility` c JOIN `tabCard Rate Agreement` p ON p.name = c.parent
WHERE c.parenttype = 'Card Rate Agreement' AND c.parentfield = 'responsibilities'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Equipment Needs Request' AS doctype, p.name AS parent, 'Equipment Needs Request Item' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabEquipment Needs Request Item` c JOIN `tabEquipment Needs Request` p ON p.name = c.parent
WHERE c.parenttype = 'Equipment Needs Request' AND c.parentfield = 'items'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Equipment Needs Review' AS doctype, p.name AS parent, 'Equipment Needs Review Item' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabEquipment Needs Review Item` c JOIN `tabEquipment Needs Review` p ON p.name = c.parent
WHERE c.parenttype = 'Equipment Needs Review' AND c.parentfield = 'items'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Equipment Transport' AS doctype, p.name AS parent, 'Equipment Transport Item' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabEquipment Transport Item` c JOIN `tabEquipment Transport` p ON p.name = c.parent
WHERE c.parenttype = 'Equipment Transport' AND c.parentfield = 'items'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'GL Posting Log' AS doctype, p.name AS parent, 'GL Posting Source' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabGL Posting Source` c JOIN `tabGL Posting Log` p ON p.name = c.parent
WHERE c.parenttype = 'GL Posting Log' AND c.parentfield = 'sources'
  AND c.docstatus <> p.docstatus
UNION ALL
SELECT 'Project Diesel Fill' AS doctype, p.name AS parent, 'Diesel Fill Equipment' AS child_doctype, c.name AS row_name, c.docstatus AS row_docstatus, p.docstatus AS parent_docstatus
FROM `tabDiesel Fill Equipment` c JOIN `tabProject Diesel Fill` p ON p.name = c.parent
WHERE c.parenttype = 'Project Diesel Fill' AND c.parentfield = 'equipment_filled'
  AND c.docstatus <> p.docstatus
ORDER BY 1, 2;
```

## Check 5 — rows outside their table or without a document

```sql
SELECT 'Card Daily Log Row' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Daily Log Row` c
WHERE NOT (c.parenttype = 'Card Daily Log' AND c.parentfield = 'rows')
   OR NOT EXISTS (SELECT 1 FROM `tabCard Daily Log` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Card Equipment Component' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Equipment Component` c
WHERE NOT (c.parenttype = 'Card Equipment' AND c.parentfield = 'components')
   OR NOT EXISTS (SELECT 1 FROM `tabCard Equipment` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Card Consumption Rate' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Consumption Rate` c
WHERE NOT (c.parenttype = 'Card Equipment' AND c.parentfield = 'consumption_rates')
   OR NOT EXISTS (SELECT 1 FROM `tabCard Equipment` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Card Type Consumption Rate' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Type Consumption Rate` c
WHERE NOT (c.parenttype = 'Card Equipment Type' AND c.parentfield = 'default_consumption_rates')
   OR NOT EXISTS (SELECT 1 FROM `tabCard Equipment Type` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Card Monthly Card Day' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Monthly Card Day` c
WHERE NOT (c.parenttype = 'Card Monthly Card' AND c.parentfield = 'days')
   OR NOT EXISTS (SELECT 1 FROM `tabCard Monthly Card` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Card Monthly Card Adjustment' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Monthly Card Adjustment` c
WHERE NOT (c.parenttype = 'Card Monthly Card' AND c.parentfield = 'adjustments')
   OR NOT EXISTS (SELECT 1 FROM `tabCard Monthly Card` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Card Period Run Source' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Period Run Source` c
WHERE NOT (c.parenttype = 'Card Period Run' AND c.parentfield = 'sources')
   OR NOT EXISTS (SELECT 1 FROM `tabCard Period Run` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Card Agreement Responsibility' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Agreement Responsibility` c
WHERE NOT (c.parenttype = 'Card Rate Agreement' AND c.parentfield = 'responsibilities')
   OR NOT EXISTS (SELECT 1 FROM `tabCard Rate Agreement` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Card Company Settings' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Company Settings` c
WHERE NOT (c.parenttype = 'Card Settings' AND c.parentfield = 'company_settings')
UNION ALL
SELECT 'Card Diesel Price' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Diesel Price` c
WHERE NOT (c.parenttype = 'Card Settings' AND c.parentfield = 'diesel_price_schedule')
UNION ALL
SELECT 'Card Project Transport Price' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Project Transport Price` c
WHERE NOT (c.parenttype = 'Card Settings' AND c.parentfield = 'project_transport_prices')
UNION ALL
SELECT 'Card Adjustment Type' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Adjustment Type` c
WHERE NOT (c.parenttype = 'Card Settings' AND c.parentfield = 'adjustment_types')
UNION ALL
SELECT 'Card Location Cost Center' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabCard Location Cost Center` c
WHERE NOT (c.parenttype = 'Card Settings' AND c.parentfield = 'location_cost_centers')
UNION ALL
SELECT 'Equipment Needs Request Item' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabEquipment Needs Request Item` c
WHERE NOT (c.parenttype = 'Equipment Needs Request' AND c.parentfield = 'items')
   OR NOT EXISTS (SELECT 1 FROM `tabEquipment Needs Request` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Equipment Needs Review Item' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabEquipment Needs Review Item` c
WHERE NOT (c.parenttype = 'Equipment Needs Review' AND c.parentfield = 'items')
   OR NOT EXISTS (SELECT 1 FROM `tabEquipment Needs Review` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Equipment Transport Item' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabEquipment Transport Item` c
WHERE NOT (c.parenttype = 'Equipment Transport' AND c.parentfield = 'items')
   OR NOT EXISTS (SELECT 1 FROM `tabEquipment Transport` p WHERE p.name = c.parent)
UNION ALL
SELECT 'GL Posting Source' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabGL Posting Source` c
WHERE NOT (c.parenttype = 'GL Posting Log' AND c.parentfield = 'sources')
   OR NOT EXISTS (SELECT 1 FROM `tabGL Posting Log` p WHERE p.name = c.parent)
UNION ALL
SELECT 'Diesel Fill Equipment' AS child_doctype, c.name AS row_name, c.parenttype, c.parent, c.parentfield
FROM `tabDiesel Fill Equipment` c
WHERE NOT (c.parenttype = 'Project Diesel Fill' AND c.parentfield = 'equipment_filled')
   OR NOT EXISTS (SELECT 1 FROM `tabProject Diesel Fill` p WHERE p.name = c.parent)
ORDER BY 1, 2;
```

## What to do with a hit

1. Open the receiving document's Version history: a moved row appears as an **added** row whose `creation` is older
   than that Version. Open the original document's Version history: the row is listed there at submit.
2. Record the finding (document names, row name, user, time) in a private note. Do not post it in a public issue.
3. Any correction is a separate, approved change on Production (approval, backup, rollback plan, per the change
   policy). This page does not correct anything.
