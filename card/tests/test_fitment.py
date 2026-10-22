# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Catalog phase 2a (FR-077): equipment make / model masters, the make / model Links on
Card Equipment and the part fitment rows with their review rules (Owner decisions Q1-Q11,
2026-10-23). Every case runs as a real user with the real DocPerms; the data is rolled
back. The two-connection races are in test_fitment_concurrency.py."""

from unittest.mock import patch

import frappe
from frappe.client import save as rest_save
from frappe.client import set_value as rest_set_value
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from card.fitment import CONFIRMED, NOT_COMPATIBLE, PENDING, SECOND_REVIEW, normalise
from card.tests.test_controllers import _ensure_masters

PART = "Card Equipment Part"
REFUSED = (frappe.PermissionError, frappe.ValidationError)


def _skip_lookup(doctype):
	"""The controller's duplicate lookup sees nothing, as when two saves check at the
	same moment; every other read works as usual."""
	original = frappe.db.get_value

	def get_value(dt, *args, **kwargs):
		return None if dt == doctype else original(dt, *args, **kwargs)

	return patch.object(frappe.db, "get_value", side_effect=get_value)


class FitmentTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=6)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		self.group = self._group()
		self.make = self._make("Komatsu")
		self.model = self._model("PC200-8")
		self.item = self._item("FILTER")
		self.machine = self._machine(equipment_model=self.model)
		self.manager = self._user("mgr", ["Card Manager"])
		self.manager_b = self._user("mgrb", ["Card Manager"])
		self.supervisor = self._user("sup", ["Card Supervisor"])
		self.card_user = self._user("usr", ["Card User"])

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- builders (Administrator) ----------

	def _group(self):
		name = f"FIT-GRP-{self.token}"
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": name, "parent_item_group": "All Item Groups"}
		).insert(ignore_permissions=True)
		return name

	def _make(self, label, **values):
		doc = frappe.get_doc(
			{"doctype": "Card Equipment Make", "make_name": f"{label} {self.token}", **values}
		)
		return doc.insert(ignore_permissions=True).name

	def _model(self, label, make=None, etype=None, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Card Equipment Model",
				"model_name": f"{label} {self.token}",
				"equipment_make": make or self.make,
				"equipment_type": etype or self.etype,
				**values,
			}
		)
		return doc.insert(ignore_permissions=True).name

	def _item(self, label, **values):
		code = f"FIT-{label}-{self.token}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": f"Fitment {label} {self.token}",
				"item_group": self.group,
				"stock_uom": "Nos",
				"is_stock_item": 1,
				**values,
			}
		).insert(ignore_permissions=True)
		return code

	def _machine(self, company=None, equipment_model=None, **values):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company or self.company
		eq.equipment_type = self.etype
		eq.equipment_name = f"FIT-EQ-{frappe.generate_hash(length=6)}"
		eq.ownership = "ملك"
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.brand = "Komatsu"
		eq.model = "PC200-8"
		eq.equipment_model = equipment_model
		eq.update(values)
		eq.insert(ignore_permissions=True)
		return eq.name

	def _user(self, prefix, roles):
		email = f"fit-{prefix}-{self.token}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": f"Fitment {prefix}",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		return email

	def _evidence_file(self, private=1):
		doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"evidence-{frappe.generate_hash(length=6)}.txt",
				"content": b"parts book page 12",
				"is_private": private,
			}
		).insert(ignore_permissions=True)
		return doc.file_url

	def _row(self, user, **values):
		"""A new fitment row inserted by ``user`` with the user's own rights."""
		frappe.set_user(user)
		try:
			doc = frappe.get_doc(
				{
					"doctype": PART,
					"item_code": self.item,
					"applies_to": "Equipment Model",
					"equipment_model": self.model,
					**values,
				}
			)
			return doc.insert()
		finally:
			frappe.set_user("Administrator")

	def _decide(self, user, name, status, **values):
		frappe.set_user(user)
		try:
			doc = frappe.get_doc(PART, name)
			doc.compatibility_status = status
			doc.evidence_source = values.pop("evidence_source", "Maker parts book")
			doc.evidence_reference = values.pop("evidence_reference", "Parts book p.12")
			doc.update(values)
			doc.save()
			return doc
		finally:
			frappe.set_user("Administrator")

	def _reload(self, name):
		return frappe.get_doc(PART, name)


class TestEquipmentMakeModel(FitmentTestCase):
	def test_normalise(self):
		self.assertEqual(normalise(" pc 200-8 "), normalise("PC200_8"))
		self.assertEqual(normalise("PC200.8/A"), "PC2008A")

	def test_duplicate_make_refused(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc({"doctype": "Card Equipment Make", "make_name": f" komatsu  {self.token}"}).insert(
				ignore_permissions=True
			)

	def test_duplicate_model_refused_written_another_way(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			self._model("pc 200 8")
		other_make = self._make("Caterpillar")
		self.assertTrue(self._model("PC200-8", make=other_make))  # same text, other make: allowed

	def test_unique_keys_hold_without_the_controller_check(self):
		"""Two saves that both pass the controller check at the same time: the unique
		index still refuses the second (the race itself: test_fitment_concurrency)."""
		with _skip_lookup("Card Equipment Make"):
			with self.assertRaises(frappe.UniqueValidationError):
				frappe.get_doc(
					{"doctype": "Card Equipment Make", "make_name": f"KOMATSU {self.token}"}
				).insert(ignore_permissions=True)

	def test_disabled_make_refused_on_a_new_model(self):
		disabled = self._make("Old", disabled=1)
		with self.assertRaises(frappe.ValidationError):
			self._model("D155", make=disabled)

	def test_make_and_type_of_a_used_model_cannot_change(self):
		doc = frappe.get_doc("Card Equipment Model", self.model)
		doc.equipment_make = self._make("Volvo")
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_used_make_cannot_be_deleted(self):
		with self.assertRaises(frappe.LinkExistsError):
			frappe.delete_doc("Card Equipment Make", self.make, ignore_permissions=True)

	def test_no_role_may_delete_and_card_user_reads_only(self):
		for doctype in ("Card Equipment Make", "Card Equipment Model", PART):
			for perm in frappe.get_meta(doctype).permissions:
				self.assertFalse(perm.delete, f"{doctype}: {perm.role} has delete")
		frappe.set_user(self.card_user)
		self.assertTrue(frappe.has_permission("Card Equipment Model", "read"))
		self.assertFalse(frappe.has_permission("Card Equipment Model", "create"))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": "Card Equipment Make", "make_name": f"Hitachi {self.token}"}).insert()

	def test_manager_creates_a_make_and_model(self):
		frappe.set_user(self.manager)
		make = frappe.get_doc(
			{"doctype": "Card Equipment Make", "make_name": f"Hitachi {self.token}"}
		).insert()
		model = frappe.get_doc(
			{
				"doctype": "Card Equipment Model",
				"model_name": "ZX200",
				"equipment_make": make.name,
				"equipment_type": self.etype,
			}
		).insert()
		self.assertTrue(make.name.startswith("CMK-"))
		self.assertTrue(model.name.startswith("CEM-"))
		self.assertEqual(model.model_key, f"{make.name}|ZX200")


class TestEquipmentLinks(FitmentTestCase):
	def test_make_is_filled_from_the_model_and_text_fields_kept(self):
		eq = frappe.get_doc("Card Equipment", self.machine)
		self.assertEqual(eq.equipment_make, self.make)
		self.assertEqual((eq.brand, eq.model), ("Komatsu", "PC200-8"))

	def test_model_of_another_make_refused(self):
		eq = frappe.get_doc("Card Equipment", self.machine)
		eq.equipment_make = self._make("Volvo")
		with self.assertRaises(frappe.ValidationError):
			eq.save(ignore_permissions=True)

	def test_model_of_another_type_refused(self):
		other_type = frappe.get_doc(
			{
				"doctype": "Card Equipment Type",
				"equipment_type_name": f"FIT-TYPE-{self.token}",
				"equipment_category": frappe.db.get_value(
					"Card Equipment Type", self.etype, "equipment_category"
				),
			}
		).insert(ignore_permissions=True)
		model = self._model("D6", etype=other_type.name)
		eq = frappe.get_doc("Card Equipment", self.machine)
		eq.equipment_model = model
		with self.assertRaises(frappe.ValidationError):
			eq.save(ignore_permissions=True)

	def test_disabled_model_refused_when_set(self):
		model = self._model("PC300", disabled=1)
		with self.assertRaises(frappe.ValidationError):
			self._machine(equipment_model=model)

	def test_card_user_cannot_set_the_model(self):
		machine = self._machine()
		frappe.set_user(self.card_user)
		doc = frappe.get_doc("Card Equipment", machine).as_dict()
		doc["equipment_model"] = self.model
		doc["equipment_make"] = self.make
		rest_save(doc)
		frappe.set_user("Administrator")
		self.assertIsNone(frappe.db.get_value("Card Equipment", machine, "equipment_model"))
		self.assertIsNone(frappe.db.get_value("Card Equipment", machine, "equipment_make"))

	def test_type_change_clears_a_model_that_no_longer_applies(self):
		"""The type follows a linked Asset's category on every save; a model of the old
		type is cleared instead of blocking the save."""
		other_type = frappe.get_doc(
			{
				"doctype": "Card Equipment Type",
				"equipment_type_name": f"FIT-TYPE2-{self.token}",
				"equipment_category": frappe.db.get_value(
					"Card Equipment Type", self.etype, "equipment_category"
				),
			}
		).insert(ignore_permissions=True)
		eq = frappe.get_doc("Card Equipment", self.machine)
		eq.equipment_type = other_type.name
		eq.save(ignore_permissions=True)
		self.assertIsNone(eq.equipment_model)
		self.assertEqual(eq.equipment_make, self.make)

	def test_existing_equipment_without_model_saves_unchanged(self):
		machine = self._machine()
		doc = frappe.get_doc("Card Equipment", machine)
		doc.plate_no = "ABC-1"
		doc.save(ignore_permissions=True)
		self.assertIsNone(doc.equipment_model)


class TestFitmentRows(FitmentTestCase):
	def test_new_row_is_pending_whatever_the_client_sends(self):
		with self.assertRaises(frappe.ValidationError):
			self._row(self.supervisor, compatibility_status=CONFIRMED)
		row = self._row(self.supervisor, proposed_by=self.manager, confirmed_by=self.manager)
		self.assertEqual(row.compatibility_status, PENDING)
		self.assertEqual(row.proposed_by, self.supervisor)
		self.assertIsNone(row.confirmed_by)
		self.assertEqual(row.source, "Supervisor proposal")
		self.assertEqual(row.compat_key, f"M|{self.model}|{self.item}")
		self.assertTrue(row.name.startswith("CFP-"))

	def test_manager_decides_a_supervisor_proposal(self):
		row = self._row(self.supervisor)
		doc = self._decide(self.manager, row.name, CONFIRMED)
		self.assertEqual(doc.compatibility_status, CONFIRMED)
		self.assertEqual(doc.confirmed_by, self.manager)
		self.assertFalse(doc.review_stage)

	def test_decision_needs_evidence(self):
		row = self._row(self.supervisor)
		with self.assertRaises(frappe.ValidationError):
			self._decide(self.manager, row.name, CONFIRMED, evidence_reference="")

	def test_own_proposal_never_becomes_final(self):
		row = self._row(self.manager)
		# no reason or no file: refused
		with self.assertRaises(frappe.ValidationError):
			self._decide(self.manager, row.name, CONFIRMED, evidence_file=self._evidence_file())
		with self.assertRaises(frappe.ValidationError):
			self._decide(self.manager, row.name, CONFIRMED, decision_reason="seen on site")
		doc = self._decide(
			self.manager,
			row.name,
			CONFIRMED,
			decision_reason="seen on site",
			evidence_file=self._evidence_file(),
		)
		self.assertEqual(doc.compatibility_status, PENDING)
		self.assertEqual(doc.review_stage, SECOND_REVIEW)
		self.assertEqual((doc.first_review_by, doc.first_review_decision), (self.manager, CONFIRMED))
		self.assertIsNone(doc.confirmed_by)
		# the proposer cannot finish their own review either
		again = self._decide(self.manager, row.name, CONFIRMED, decision_reason="seen twice")
		self.assertEqual(again.compatibility_status, PENDING)
		# an independent second reviewer decides
		final = self._decide(self.manager_b, row.name, CONFIRMED)
		self.assertEqual(final.compatibility_status, CONFIRMED)
		self.assertEqual(final.confirmed_by, self.manager_b)
		self.assertFalse(final.review_stage)
		self.assertEqual(final.first_review_by, self.manager)  # the first review stays on record

	def test_administrator_is_not_exempt(self):
		row = self._row("Administrator")
		doc = self._decide(
			"Administrator",
			row.name,
			NOT_COMPATIBLE,
			decision_reason="parts book",
			evidence_file=self._evidence_file(),
		)
		self.assertEqual(doc.compatibility_status, PENDING)
		self.assertEqual(doc.review_stage, SECOND_REVIEW)

	def test_second_reviewer_may_send_the_first_review_back(self):
		row = self._row(self.manager)
		self._decide(
			self.manager, row.name, CONFIRMED, decision_reason="seen", evidence_file=self._evidence_file()
		)
		doc = self._decide(self.manager_b, row.name, PENDING, decision_reason="wrong page in the book")
		self.assertEqual(doc.compatibility_status, PENDING)
		self.assertFalse(doc.review_stage)
		self.assertIsNone(doc.confirmed_by)  # sent back: nobody decided (Version keeps who)

	def test_proposer_change_of_a_decided_row_goes_back_to_review(self):
		row = self._row(self.manager)
		self._decide(self.manager_b, row.name, CONFIRMED)
		doc = self._decide(
			self.manager,
			row.name,
			NOT_COMPATIBLE,
			decision_reason="wrong size",
			evidence_file=self._evidence_file(),
		)
		self.assertEqual(doc.compatibility_status, PENDING)
		self.assertEqual(doc.review_stage, SECOND_REVIEW)

	def test_rest_paths_follow_the_same_rules(self):
		row = self._row(self.manager)
		frappe.set_user(self.manager)
		# frappe.client.set_value: the proposer's decision is not applied
		with self.assertRaises(frappe.ValidationError):
			rest_set_value(
				PART,
				row.name,
				{"compatibility_status": CONFIRMED, "evidence_source": "Other", "evidence_reference": "x"},
			)
		# /api/resource PUT (frappe.client.save): server-owned fields from the client are ignored
		doc = frappe.get_doc(PART, row.name).as_dict()
		doc.update(
			{
				"compatibility_status": CONFIRMED,
				"confirmed_by": self.manager_b,
				"proposed_by": self.manager_b,
				"evidence_source": "Other",
				"evidence_reference": "x",
				"decision_reason": "rest",
				"evidence_file": self._evidence_file(),
			}
		)
		saved = rest_save(doc)
		frappe.set_user("Administrator")
		self.assertEqual(saved["compatibility_status"], PENDING)
		self.assertEqual(saved["proposed_by"], self.manager)
		self.assertEqual(saved["review_stage"], SECOND_REVIEW)
		self.assertIsNone(saved["confirmed_by"])

	def test_supervisor_limits(self):
		row = self._row(self.supervisor)
		with self.assertRaises(frappe.ValidationError):
			self._decide(self.supervisor, row.name, CONFIRMED)
		# own pending row: evidence may be added
		frappe.set_user(self.supervisor)
		doc = frappe.get_doc(PART, row.name)
		doc.evidence_reference = "Dealer letter 7"
		doc.save()
		frappe.set_user("Administrator")
		# a row proposed by another user: refused
		other = self._row(self.manager, item_code=self._item("BELT"))
		frappe.set_user(self.supervisor)
		doc = frappe.get_doc(PART, other.name)
		doc.technical_notes = "x"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		frappe.set_user("Administrator")
		# own row after a decision: refused
		self._decide(self.manager, row.name, CONFIRMED)
		frappe.set_user(self.supervisor)
		doc = frappe.get_doc(PART, row.name)
		doc.qty_per_use = 2
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_duplicate_row_refused_and_retired_row_named(self):
		row = self._row(self.supervisor)
		with self.assertRaises(frappe.DuplicateEntryError):
			self._row(self.manager)
		self._retire(row.name)
		with self.assertRaises(frappe.DuplicateEntryError) as ctx:
			self._row(self.manager)
		self.assertIn(row.name, str(ctx.exception))

	def test_unique_key_holds_without_the_controller_check(self):
		self._row(self.supervisor)
		frappe.set_user("Administrator")
		with _skip_lookup(PART):
			with self.assertRaises(frappe.UniqueValidationError):
				self._row(self.manager)

	def test_key_fields_cannot_change(self):
		row = self._row(self.supervisor)
		frappe.set_user(self.manager)
		doc = frappe.get_doc(PART, row.name)
		doc.item_code = self._item("OTHER")
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_machine_row_takes_company_and_model_from_the_machine(self):
		row = self._row(
			self.supervisor, applies_to="Equipment", card_equipment=self.machine, equipment_model=None
		)
		self.assertEqual(row.company, self.company)
		self.assertEqual(row.equipment_model, self.model)
		self.assertEqual(row.compat_key, f"E|{self.machine}|{self.item}")
		model_row = self._row(self.supervisor)
		self.assertIsNone(model_row.company)
		self.assertIsNone(model_row.card_equipment)

	def test_item_rules(self):
		for values in (
			{"disabled": 1},
			{"has_variants": 1, "attributes": []},
			{"end_of_life": add_days(nowdate(), -1)},
		):
			try:
				code = self._item(frappe.generate_hash(length=4), **values)
			except frappe.ValidationError:
				continue  # ERPNext itself refused the setup (template without attributes)
			with self.assertRaises(frappe.ValidationError, msg=str(values)):
				self._row(self.manager, item_code=code)

	def test_machine_confirmed_against_model_not_compatible_needs_notes(self):
		model_row = self._row(self.supervisor)
		self._decide(self.manager, model_row.name, NOT_COMPATIBLE)
		machine_row = self._row(self.supervisor, applies_to="Equipment", card_equipment=self.machine)
		with self.assertRaises(frappe.ValidationError):
			self._decide(self.manager, machine_row.name, CONFIRMED)
		doc = self._decide(
			self.manager, machine_row.name, CONFIRMED, technical_notes="later serials use the new filter"
		)
		self.assertEqual(doc.compatibility_status, CONFIRMED)

	def test_delete_refused_for_everyone(self):
		row = self._row(self.supervisor)
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc(PART, row.name, ignore_permissions=True)

	def _retire(self, name, user=None, reason="superseded part"):
		frappe.set_user(user or self.manager)
		try:
			doc = frappe.get_doc(PART, name)
			doc.is_active = 0
			doc.retire_reason = reason
			doc.save()
			return doc
		finally:
			frappe.set_user("Administrator")

	def test_retire_and_restore(self):
		row = self._row(self.supervisor)
		self._decide(self.manager, row.name, CONFIRMED)
		with self.assertRaises(frappe.ValidationError):
			self._retire(row.name, reason="")
		with self.assertRaises(frappe.ValidationError):
			self._retire(row.name, user=self.supervisor)
		doc = self._retire(row.name)
		self.assertEqual((doc.is_active, doc.retired_by), (0, self.manager))
		frappe.set_user(self.manager_b)
		doc = frappe.get_doc(PART, row.name)
		doc.is_active = 1
		doc.save()
		frappe.set_user("Administrator")
		self.assertEqual(doc.compatibility_status, PENDING)  # restored rows are reviewed again

	def test_history_is_kept(self):
		row = self._row(self.supervisor)
		frappe.set_user(self.manager)
		doc = frappe.get_doc(PART, row.name)
		doc.update(
			{
				"compatibility_status": CONFIRMED,
				"evidence_source": "Maker parts book",
				"evidence_reference": "p.12",
			}
		)
		doc.save(ignore_version=False)  # tests skip Version rows unless asked (frappe.in_test)
		frappe.set_user("Administrator")
		version = frappe.get_all("Version", filters={"ref_doctype": PART, "docname": row.name}, pluck="data")
		self.assertEqual(len(version), 1)
		self.assertIn(CONFIRMED, version[0])
		self.assertIn("confirmed_by", version[0])

	def test_evidence_file_must_be_private(self):
		row = self._row(self.supervisor)
		with self.assertRaises(frappe.ValidationError):
			self._decide(self.manager, row.name, CONFIRMED, evidence_file=self._evidence_file(private=0))
		with self.assertRaises(frappe.ValidationError):
			self._decide(self.manager, row.name, CONFIRMED, evidence_file="/private/files/not-uploaded.pdf")

	def test_new_evidence_on_a_decided_row_needs_a_new_review(self):
		row = self._row(self.supervisor)
		self._decide(self.manager, row.name, CONFIRMED)
		frappe.set_user(self.manager)
		doc = frappe.get_doc(PART, row.name)
		doc.evidence_reference = "Another book p.40"
		doc.save()
		frappe.set_user("Administrator")
		self.assertEqual(doc.compatibility_status, PENDING)
		self.assertIsNone(doc.confirmed_by)

	def test_machine_row_model_follows_the_machine(self):
		row = self._row(self.supervisor, applies_to="Equipment", card_equipment=self.machine)
		other = self._model("PC210")
		eq = frappe.get_doc("Card Equipment", self.machine)
		eq.equipment_model = other
		eq.save(ignore_permissions=True)
		doc = self._decide(self.manager, row.name, CONFIRMED)
		self.assertEqual(doc.equipment_model, other)

	def test_empty_and_missing_key_values_are_the_same(self):
		row = self._row(self.supervisor)
		frappe.set_user(self.supervisor)
		doc = frappe.get_doc(PART, row.name).as_dict()
		doc.update({"card_equipment": "", "technical_notes": "rest client"})
		saved = rest_save(doc)
		frappe.set_user("Administrator")
		self.assertEqual(saved["technical_notes"], "rest client")


class TestFitmentAccess(FitmentTestCase):
	def _other_company(self):
		name = "TEST-FIT-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "F" + self.token[:5].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _restrict(self, user, company):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Company",
				"for_value": company,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=user)

	def test_card_user_has_no_access_to_rows_or_evidence(self):
		row = self._row(self.supervisor)
		url = self._evidence_file()
		file_doc = frappe.get_doc("File", {"file_url": url})
		file_doc.attached_to_doctype, file_doc.attached_to_name = PART, row.name
		file_doc.save(ignore_permissions=True)
		frappe.set_user(self.card_user)
		self.assertFalse(frappe.has_permission(PART, "read", row.name))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list(PART)
		self.assertFalse(frappe.has_permission("File", "read", file_doc.name))
		frappe.set_user(self.supervisor)
		self.assertTrue(frappe.has_permission("File", "read", file_doc.name))

	def test_machine_rows_of_another_company_are_hidden(self):
		other = self._other_company()
		machine_b = self._machine(company=other)
		row_b = self._row("Administrator", applies_to="Equipment", card_equipment=machine_b)
		row_a = self._row("Administrator", applies_to="Equipment", card_equipment=self.machine)
		model_row = self._row("Administrator")
		self._restrict(self.manager, self.company)
		frappe.set_user(self.manager)
		names = set(frappe.get_list(PART, pluck="name"))
		self.assertIn(row_a.name, names)
		self.assertIn(model_row.name, names)
		self.assertNotIn(row_b.name, names)
		self.assertFalse(frappe.has_permission(PART, "read", row_b.name))
		with self.assertRaises(REFUSED):
			frappe.get_doc(
				{
					"doctype": PART,
					"item_code": self._item("X"),
					"applies_to": "Equipment",
					"card_equipment": machine_b,
				}
			).insert()

	def test_machine_with_fitment_rows_keeps_its_company(self):
		self._row("Administrator", applies_to="Equipment", card_equipment=self.machine)
		eq = frappe.get_doc("Card Equipment", self.machine)
		eq.company = self._other_company()
		with self.assertRaises(frappe.ValidationError):
			eq.save(ignore_permissions=True)

	def test_report_is_read_only_and_for_managers(self):
		from card.card.report.equipment_make_model_values.equipment_make_model_values import execute

		self._machine()
		self._machine(brand="komatsu ", model="pc 200 8")
		roles = {r.role for r in frappe.get_doc("Report", "Equipment Make Model Values").roles}
		self.assertEqual(roles, {"Card Manager", "System Manager"})
		frappe.set_user(self.manager)
		columns, data = execute({"unlinked_only": 1})
		frappe.set_user("Administrator")
		groups = [r for r in data if normalise(r["model"]) == "PC2008" and normalise(r["brand"]) == "KOMATSU"]
		self.assertEqual(len(groups), 1)
		self.assertGreaterEqual(groups[0]["equipment_count"], 2)
		self.assertNotIn("rate", {c["fieldname"] for c in columns})

	def test_sidebar_rows(self):
		items = frappe.get_all(
			"Sidebar Item", filters={"parent": "Card Materials", "parenttype": "Sidebar"}, pluck="link_to"
		)
		for doctype in ("Card Equipment Make", "Card Equipment Model", PART):
			self.assertEqual(items.count(doctype), 1, doctype)
