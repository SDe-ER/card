# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""WS-013: the v4.1.3 patch removes only the site Translations that translate the
application name "Card", and a second run changes nothing."""

import frappe
from frappe.tests import IntegrationTestCase

from card.patches.v4_1_3 import remove_app_name_translations


class TestRemoveAppNameTranslations(IntegrationTestCase):
	def _translation(self, language, source, translated, context=None):
		return (
			frappe.get_doc(
				doctype="Translation",
				language=language,
				source_text=source,
				translated_text=translated,
				context=context,
			)
			.insert()
			.name
		)

	def test_only_the_app_name_translations_are_removed(self):
		removed = [
			self._translation("ar", "Card", "كارت"),
			self._translation("fa", "Card", "کارت"),
			self._translation("en", "Card", "Card"),
		]
		kept = [
			self._translation("ar", "Card Equipment", "المعدات"),
			self._translation("ar", "card", "بطاقة"),
			self._translation("ar", "Card", "بطاقة", context="Number Card Link"),
			self._translation("fr", "Card", "CARD"),
		]

		remove_app_name_translations.execute()

		for name in removed:
			self.assertFalse(frappe.db.exists("Translation", name), name)
			self.assertTrue(
				frappe.db.exists("Deleted Document", {"deleted_doctype": "Translation", "deleted_name": name})
			)
		for name in kept:
			self.assertTrue(frappe.db.exists("Translation", name), name)

		before = frappe.get_all("Translation", pluck="name", order_by="name")
		remove_app_name_translations.execute()
		self.assertEqual(frappe.get_all("Translation", pluck="name", order_by="name"), before)
