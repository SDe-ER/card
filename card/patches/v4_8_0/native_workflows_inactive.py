# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""v4.8.0 (FR-152, #35 G1; closure plan C-14): the native approval Workflows of Card Monthly Card, Equipment
Transport and Project Diesel Fill, created INACTIVE when missing, and the ``workflow_state`` of existing records.

- The same idempotent ``ensure_workflows()`` as ``after_install``: an existing Workflow, Workflow State or Workflow
  Action Master is never changed, a new Workflow is inactive. Activating it is an owner setup action (W-16).
- A Custom Field ``workflow_state`` that an earlier Workflow created on these DocTypes is removed (the DocTypes now
  carry the standard field; the column and its values stay).
- Existing records get a state from their docstatus, written with a query (no document hook, docstatus and
  ``modified`` unchanged): drafts -> Draft, submitted -> "Approved – before governance", cancelled -> Cancelled.
  A record that already holds a state of its Workflow with the same docstatus keeps it, so a second migrate
  changes nothing."""

from card.governance_workflows import backfill_states, ensure_workflows, remove_duplicate_state_custom_fields


def execute():
	remove_duplicate_state_custom_fields()
	ensure_workflows()
	backfill_states()
