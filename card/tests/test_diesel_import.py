# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-086 (Owner 2026-10-26): reviewed WhatsApp sessions become draft fills with private meter photos.
One fill per source key, photos checked against the manifest, company price only, never approved."""

import hashlib
import io
import json
import os
import shutil
import tempfile

import frappe
from frappe.tests import IntegrationTestCase
from PIL import Image

from card.diesel_import import import_sessions
from card.tests.diesel_price import set_diesel_price
from card.tests.test_controllers import _ensure_masters
from card.tests.test_settings_wiring import _role_user, _set

DOCTYPE = "Project Diesel Fill"


class TestDieselImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		_set("period_lock_date", None)
		_set("diesel_supplier", None)
		_set("diesel_supplier_policy", "متغير")
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-DIM-PRJ-" + self.token
		proj.company = self.company
		self.project = proj.insert(ignore_permissions=True).name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DIM-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		self.supplier = sup.insert(ignore_permissions=True).name
		set_diesel_price(self.company, 1.79)
		self.dir = tempfile.mkdtemp(prefix="card-dim-")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		shutil.rmtree(self.dir, ignore_errors=True)
		# the rollback removes the File rows, not the files written to the site folder
		folder = frappe.get_site_path("private", "files")
		for name in os.listdir(folder):
			if self.token in name:
				os.remove(os.path.join(folder, name))

	# ---------- helpers ----------
	def _photo(self, label):
		name = f"{label}-{self.token}.jpg"
		# a real JPEG: Frappe opens image files on upload; the colour makes each photo's bytes unique
		buffer = io.BytesIO()
		seed = hashlib.sha256(f"{label}{self.token}".encode()).digest()
		Image.new("RGB", (8, 8), tuple(seed[:3])).save(buffer, "JPEG")
		content = buffer.getvalue()
		with open(os.path.join(self.dir, name), "wb") as f:
			f.write(content)
		return {"photo": name, "sha256": hashlib.sha256(content).hexdigest()}

	def _session(self, key="A", closing=1702, **extra):
		session = {
			"source_key": f"WA-TEST-{key}-{self.token}",
			"company": self.company,
			"project": self.project,
			"supplier": self.supplier,
			"date": "2026-08-25",
			"opening": {
				"reading": 0,
				"totalizer": "0556232",
				"time": "2026-08-25 06:50:05",
				**self._photo(key + "o"),
			},
			"closing": {
				"reading": closing,
				"totalizer": "055793?",
				"time": "2026-08-25 07:50:56",
				**self._photo(key + "c"),
			},
			"photo_location": "test site",
			"messages": [f"WA-TEST-{key}-1", f"WA-TEST-{key}-2"],
			"caption": "test caption / 3 excavators",
			"equipment": ["3 excavators", "1 loader"],
			"unit_price": 1.79,
		}
		session.update(extra)
		return session

	def _run(self, sessions, dry_run=0):
		path = os.path.join(self.dir, f"manifest-{frappe.generate_hash(length=6)}.json")
		with open(path, "w", encoding="utf-8") as f:
			json.dump(sessions, f)
		return import_sessions(path, self.dir, dry_run=dry_run, commit=0)

	def _fills(self):
		return frappe.get_all(DOCTYPE, filters={"project": self.project}, pluck="name")

	# ---------- tests ----------
	def test_creates_a_draft_fill_with_private_photos(self):
		ledger = {
			dt: frappe.db.count(dt)
			for dt in ("Purchase Invoice", "Payment Entry", "Journal Entry", "GL Entry")
		}
		session = self._session()
		out = self._run([session])
		row = out["results"][0]
		self.assertEqual(row["result"], "Created", row)
		fill = frappe.get_doc(DOCTYPE, row["name"])
		self.assertEqual(fill.docstatus, 0)
		self.assertEqual(fill.litres, 1702)
		self.assertEqual(fill.unit_price, 1.79)
		self.assertNotEqual(fill.review_status, "Operations Approved")
		self.assertEqual(fill.totalizer_check, "Consistent")
		self.assertEqual(fill.source_key, f"WA-TEST-A-{self.token}")
		self.assertEqual([r.match_status for r in fill.equipment_filled], ["Unmatched", "Unmatched"])
		self.assertFalse(any(r.card_equipment for r in fill.equipment_filled))
		files = frappe.get_all(
			"File",
			filters={"attached_to_doctype": DOCTYPE, "attached_to_name": fill.name},
			fields=["file_url", "is_private"],
		)
		self.assertEqual(len(files), 2)
		self.assertTrue(all(f.is_private for f in files))
		self.assertEqual({fill.opening_photo, fill.closing_photo}, {f.file_url for f in files})
		self.assertIn(
			f"closing photo {session['closing']['photo']} SHA-256 {session['closing']['sha256']}",
			fill.source_messages,
		)
		# never an accounting document
		self.assertEqual(ledger, {dt: frappe.db.count(dt) for dt in ledger})

	def test_rerun_skips_the_existing_fill(self):
		session = self._session()
		first = self._run([session])["results"][0]
		again = self._run([session])["results"][0]
		self.assertEqual(again["result"], "Existing")
		self.assertEqual(again["name"], first["name"])
		self.assertEqual(len(self._fills()), 1)

	def test_dry_run_keeps_nothing(self):
		out = self._run([self._session()], dry_run=1)
		self.assertEqual(out["results"][0]["result"], "Would Create", out)
		self.assertEqual(out["results"][0]["litres"], 1702)
		self.assertEqual(self._fills(), [])
		self.assertFalse(frappe.get_all("File", filters={"file_name": ["like", f"%{self.token}%"]}))

	def test_photo_must_match_the_manifest_hash(self):
		session = self._session()
		session["closing"]["sha256"] = "0" * 64
		row = self._run([session])["results"][0]
		self.assertEqual(row["result"], "Error")
		self.assertIn("SHA-256", row["error"])
		self.assertEqual(self._fills(), [])

	def test_photo_name_cannot_leave_the_folder(self):
		session = self._session()
		session["closing"]["photo"] = "../" + session["closing"]["photo"]
		row = self._run([session])["results"][0]
		self.assertEqual(row["result"], "Error")
		self.assertEqual(self._fills(), [])

	def test_closing_photo_is_required(self):
		session = self._session()
		session["closing"].pop("photo")
		row = self._run([session])["results"][0]
		self.assertEqual(row["result"], "Error")
		self.assertEqual(self._fills(), [])

	def test_other_price_is_refused(self):
		row = self._run([self._session(unit_price=1.66)])["results"][0]
		self.assertEqual(row["result"], "Error")
		self.assertIn("company price", row["error"])
		self.assertEqual(self._fills(), [])

	def test_price_is_required(self):
		session = self._session()
		session.pop("unit_price")
		row = self._run([session])["results"][0]
		self.assertEqual(row["result"], "Error")
		self.assertIn("unit price", row["error"])

	def test_long_reported_name_is_kept_in_notes(self):
		name = "x" * 200
		row = self._run([self._session(equipment=[name])])["results"][0]
		self.assertEqual(row["result"], "Created", row)
		line = frappe.get_doc(DOCTYPE, row["name"]).equipment_filled[0]
		self.assertEqual((line.reported_name, line.notes), (name[:140], name))

	def test_dry_run_sees_a_photo_shared_inside_the_manifest(self):
		first = self._session("A")
		second = self._session("B")
		second["closing"] = dict(first["closing"])
		out = self._run([first, second], dry_run=1)
		self.assertEqual([r["result"] for r in out["results"]], ["Would Create", "Error"])

	def test_rejected_fill_releases_its_photo_in_the_dry_run(self):
		first = self._session("A")
		name = self._run([first])["results"][0]["name"]
		frappe.db.set_value(DOCTYPE, name, "review_status", "Rejected")
		second = self._session("B")
		second["closing"] = dict(first["closing"])
		row = self._run([second], dry_run=1)["results"][0]
		self.assertEqual(row["result"], "Would Create", row)

	def test_same_photo_cannot_prove_two_sessions(self):
		first = self._session("A")
		second = self._session("B")
		second["closing"] = dict(first["closing"])
		out = self._run([first, second])
		self.assertEqual([r["result"] for r in out["results"]], ["Created", "Error"])
		self.assertEqual(len(self._fills()), 1)
		# the failed session left no File row of its own
		self.assertEqual(
			frappe.db.count("File", {"attached_to_doctype": DOCTYPE, "file_name": first["closing"]["photo"]}),
			1,
		)

	def test_dry_run_reports_a_used_photo(self):
		first = self._session("A")
		self._run([first])
		second = self._session("B")
		second["closing"] = dict(first["closing"])
		row = self._run([second], dry_run=1)["results"][0]
		self.assertEqual(row["result"], "Error")
		self.assertIn("already used", row["error"])

	def test_one_bad_session_does_not_stop_the_others(self):
		bad = self._session("A")
		bad["closing"]["sha256"] = "0" * 64
		out = self._run([bad, self._session("B")])
		self.assertEqual([r["result"] for r in out["results"]], ["Error", "Created"])
		self.assertEqual(out["summary"], {"Error": 1, "Created": 1})

	def test_source_is_set_by_the_import_only(self):
		fill = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"company": self.company,
				"project": self.project,
				"supplier": self.supplier,
				"date": "2026-08-25",
				"litres": 100,
				"source_key": f"WA-FORGED-{self.token}",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			fill.insert()
		name = self._run([self._session()])["results"][0]["name"]
		imported = frappe.get_doc(DOCTYPE, name)
		imported.source_key = f"WA-OTHER-{self.token}"
		with self.assertRaises(frappe.ValidationError):
			imported.save()
		# other edits of an imported fill still save
		imported.reload()
		imported.remarks = "checked"
		imported.save()

	def test_card_user_cannot_import(self):
		frappe.set_user(_role_user("Card User"))
		with self.assertRaises(frappe.PermissionError):
			self._run([self._session()])
		frappe.set_user("Administrator")
		self.assertEqual(self._fills(), [])
