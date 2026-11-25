# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-142: Card Daily Log controller. The rules live in card.daily_log; company isolation of the record is the
generic FR-131 scope (card.company_scope, registered in hooks.py for this DocType)."""

from frappe.model.document import Document
from frappe.utils import cint

from card import daily_log


class CardDailyLog(Document):
	def onload(self):
		# FR-188: the form shows the load fields of a row only when the log's company uses them (a flag only)
		self.set_onload(daily_log.LOADS_SETTING, cint(daily_log.loads_enabled(self.company)))

	def validate(self):
		daily_log.prepare(self)
		daily_log.validate_log(self)

	def before_submit(self):
		daily_log.record_submitter(self)

	def before_update_after_submit(self):
		daily_log.check_transition(self)

	def before_cancel(self):
		daily_log.check_cancel(self)
