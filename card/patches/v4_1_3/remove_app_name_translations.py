# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""WS-013 (Owner, final decision 2026-11-28): the application name is "Card" in every language. A site
Translation of the source text "Card" (for example ar "Card" -> "كارت") wins over the app's
locale files, so it is removed. Only the exact source text "Card" without a context is
touched; every other Translation stays. frappe keeps each removed row as a Deleted
Document. Idempotent."""

import frappe

APP_NAME_SOURCE = "Card"
APP_NAME = "Card"


def execute():
	rows = frappe.get_all(
		"Translation",
		filters={"source_text": APP_NAME_SOURCE},
		fields=["name", "language", "source_text", "translated_text", "context"],
	)
	for row in rows:
		# the database match ignores case; "card" or a row with a context is another string
		if row.source_text != APP_NAME_SOURCE or row.context or row.translated_text == APP_NAME:
			continue
		frappe.delete_doc("Translation", row.name)
		print(f"Card WS-013: removed Translation {row.name} ({row.language}: Card -> {row.translated_text})")
