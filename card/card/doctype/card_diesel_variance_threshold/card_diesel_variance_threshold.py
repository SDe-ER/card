# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-151 (#31): one company's anomaly thresholds for the Diesel Variance Anomaly report (a row of
Card Settings ``diesel_variance_thresholds``). A company without a row gets no anomaly flags."""

from frappe.model.document import Document


class CardDieselVarianceThreshold(Document):
	pass
