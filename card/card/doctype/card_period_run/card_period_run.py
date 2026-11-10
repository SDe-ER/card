# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-147: Card Period Run controller. The rules live in card.gl.period_run; company isolation of the record is the
generic FR-131 scope (card.company_scope, registered in hooks.py for this DocType)."""

from frappe.model.document import Document

from card.gl import period_run


class CardPeriodRun(Document):
	def validate(self):
		period_run.prepare_run(self)

	def before_submit(self):
		period_run.record_submitter(self)

	def before_update_after_submit(self):
		period_run.check_transition(self)

	def before_cancel(self):
		period_run.check_cancel(self)
