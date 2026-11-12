# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-157 (#31, #47, #124; closure plan WP-G1, C-03, C-06): a Diesel Fill Allocation row is a
per-equipment estimated split of a tank-style diesel fill, frozen at submit. These rows are
report/card figures only — the GL posting of the fill is unchanged (FR-100: a tank fill posts
one project-level line, never per equipment). The parent `Project Diesel Fill` controller writes
the rows in `before_submit`, with weights from `card.diesel_fill_allocation`.

No fields are written here: the child class is a plain Document so a child-row `save` runs the
standard parent save path (the parent's `allow_on_submit` = 0 keeps a submitted fill's rows
frozen, and the FR-123 `before_cancel` guard refuses a cancel that changes the rows)."""

from frappe.model.document import Document


class DieselFillAllocation(Document):
	pass
