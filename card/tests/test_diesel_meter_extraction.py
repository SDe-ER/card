# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Meter extraction inside the existing Project Diesel Fill (Owner 2026-11-02). The worker is MOCKED: these tests
cover CARD's validation of the worker's answer, the decision table, the fill's own validate path, idempotency and
the rule that nothing is ever submitted, overwritten or written on a fill that is approved. Synthetic data only."""

import json
import socket
import uuid
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card import diesel_meter_extraction as dme
from card.diesel_meter_extraction import WorkerError, decide, validate_response
from card.tests.diesel_price import set_diesel_price
from card.tests.sample_files import png
from card.tests.test_controllers import _ensure_masters
from card.tests.test_settings_wiring import _role_user, _set

SHA = "a" * 64
MODELS = "b" * 64


def meta(side="closing", sha=SHA):
	return {"contract_version": "1.0", "request_id": str(uuid.uuid4()), "side": side, "photo_sha256": sha}


def answer(
	m,
	text="00042",
	between=(),
	unreadable=(),
	flags=(),
	status="ok",
	size=(800, 600),
	box=(100, 100, 300, 80),
):
	"""A well-formed worker answer for the request meta `m` (the synthetic vectors a-c of the contract)."""
	chars = text.replace(".", "")
	drums = []
	for i, ch in enumerate(chars):
		if ch.isdigit():
			drums.append({"pos": i, "state": "clear", "digit": int(ch), "digit_next": None, "score": 0.9})
		elif i in between:
			drums.append({"pos": i, "state": "between", "digit": 2, "digit_next": 3, "score": 0.5})
		else:
			drums.append({"pos": i, "state": "unreadable", "digit": None, "digit_next": None, "score": 0.1})
	n = len(chars)
	low = high = (
		0.0  # the contract's rule: a half-rolled drum spans one unit of its place, an unreadable one 0-9
	)
	for d in drums:
		place = 10 ** (n - 1 - d["pos"])
		low += (d["digit"] or 0) * place if d["state"] != "unreadable" else 0
		high += (
			d["digit"] * place
			if d["state"] == "clear"
			else (d["digit"] + 1) * place
			if d["state"] == "between"
			else 9 * place
		)
	if "." in text:
		low, high = low / 10, high / 10
	body = {
		"contract_version": "1.0",
		"request_id": m["request_id"],
		"photo_sha256": m["photo_sha256"],
		"engine": {"name": "synthetic", "version": "1.0", "models_hash": MODELS},
		"elapsed_ms": 5,
		"status": status,
		"window": {"found": True, "box": list(box), "image_size": list(size)},
		"layout": {"drum_count": len(chars), "decimal_present": "." in text, "confidence": 0.5},
		"drums": drums,
		"reading": {
			"text": text,
			"value": None if "?" in text else float(text),
			"interval_low": low,
			"interval_high": high,
		},
		"flags": list(flags),
	}
	return body


def reading(text="00042", side="closing", **kw):
	m = meta(side)
	return validate_response(answer(m, text, **kw), m, [800, 600])


FILL = {
	"docstatus": 0,
	"review_status": "Draft",
	"litres": 42,
	"opening_reading": 0,
	"closing_reading": 0,
	"invoiced_litres": 0,
}


class TestValidateResponse(IntegrationTestCase):
	def test_clear_reading_is_accepted_and_normalised(self):
		r = reading("00042")
		self.assertTrue(r["clear"])
		self.assertEqual((r["value"], r["low"], r["high"], r["drum_count"]), (42.0, 42.0, 42.0, 5))

	def test_half_roll_and_glare_are_never_points(self):
		half = reading("0004?", between=(4,), flags=("half_roll",))
		self.assertFalse(half["clear"])
		self.assertIsNone(half["value"])
		self.assertEqual((half["low"], half["high"]), (42.0, 43.0))
		glare = reading("0004?", unreadable=(4,), flags=("glare",))
		self.assertIsNone(glare["value"])
		self.assertEqual((glare["low"], glare["high"]), (40.0, 49.0))

	def test_defect_flag_makes_a_clear_reading_unclear(self):
		self.assertFalse(reading("00042", flags=("window_cut",))["clear"])

	def test_every_malformed_answer_is_refused(self):
		m = meta()
		good = answer(m)
		cases = {}
		cases["text_disagrees_with_drums"] = dict(
			good,
			reading=dict(good["reading"], text="00043", value=43.0, interval_low=43.0, interval_high=43.0),
		)
		cases["sha_mismatch"] = dict(good, photo_sha256="c" * 64)
		cases["request_id_mismatch"] = dict(good, request_id=str(uuid.uuid4()))
		cases["contract_version"] = dict(good, contract_version="2.0")
		cases["unknown_flag"] = dict(good, flags=["ink"])
		cases["status_enum"] = dict(good, status="maybe")
		cases["value_with_question_mark"] = dict(
			answer(m, "0004?", between=(4,)),
			reading={"text": "0004?", "value": 42.0, "interval_low": 42.0, "interval_high": 43.0},
		)
		cases["interval_widened_by_the_worker"] = dict(
			answer(m, "0004?", between=(4,)),
			reading={"text": "0004?", "value": None, "interval_low": 0.0, "interval_high": 99.0},
		)
		cases["interval_narrowed_by_the_worker"] = dict(
			answer(m, "0004?", unreadable=(4,)),
			reading={"text": "0004?", "value": None, "interval_low": 40.0, "interval_high": 41.0},
		)
		bad_next = answer(m, "0004?", between=(4,))
		bad_next["drums"][4]["digit_next"] = 7
		cases["digit_next_inconsistent"] = bad_next
		cases["overlay_unparseable"] = dict(good, overlay={"datetime": "not a date"})
		for bad in ("<svg onload=alert(1)>", "a/b", "..", "has space", "x" * 25, ""):
			cases[f"engine_version_{bad[:8]}"] = dict(
				good, engine={"name": "synthetic", "version": bad, "models_hash": MODELS}
			)
		cases["engine_name_markup"] = dict(
			good, engine={"name": "<b>", "version": "1", "models_hash": MODELS}
		)
		cases["interval_inverted"] = dict(good, reading=dict(good["reading"], interval_low=50.0))
		cases["box_outside_image"] = dict(good, window=dict(good["window"], box=[700, 100, 300, 80]))
		cases["image_size_differs"] = dict(good, window=dict(good["window"], image_size=[801, 600]))
		cases["drum_count_out_of_range"] = dict(good, layout=dict(good["layout"], drum_count=2))
		cases["decimal_mismatch"] = dict(good, layout=dict(good["layout"], decimal_present=True))
		cases["status_error"] = dict(good, status="error")
		cases["not_an_object"] = ["x"]
		cases["engine_hash"] = dict(good, engine={"name": "x", "version": "1", "models_hash": "zz"})
		for name, body in cases.items():
			with self.subTest(case=name), self.assertRaises(WorkerError):
				validate_response(body, m, [800, 600])

	def test_no_meter_and_unreadable_carry_only_status_and_flags(self):
		m = meta()
		r = validate_response({**answer(m, status="no_meter")}, m, [800, 600])
		self.assertEqual((r["status"], r["clear"], r["value"]), ("no_meter", False, None))

	def test_num_accepts_only_finite_numbers(self):
		for bad in (float("nan"), float("inf"), float("-inf"), True, False, None, "1", [1]):
			with self.subTest(value=repr(bad)), self.assertRaises(WorkerError):
				dme._num(bad)
		self.assertEqual((dme._num(5), dme._num(2.5), dme._num(0)), (5, 2.5, 0))
		with self.assertRaises(WorkerError):
			dme._num(-1, 0)  # below the minimum

	def test_call_worker_rejects_bad_http(self):
		cfg = ("http://127.0.0.1:9", "t")

		def run(status=200, ctype="application/json", body=b"{}"):
			with (
				mock.patch.object(dme, "_post", return_value=(status, ctype, body)),
				mock.patch.object(dme, "image_size_of", return_value=[800, 600]),
			):
				return dme.call_worker(cfg, "closing", SHA, b"x", "image/png")

		for kwargs in (
			{"status": 500},
			{"ctype": "text/html"},
			{"body": b"not json"},
			{"body": b"x" * (64 * 1024 + 1)},
		):
			with self.subTest(kwargs=kwargs), self.assertRaises(WorkerError):
				run(**kwargs)
		with mock.patch.object(dme, "_post", side_effect=OSError("down")), self.assertRaises(WorkerError):
			dme.call_worker(cfg, "closing", SHA, b"x", "image/png")


class TestWorkerUrl(IntegrationTestCase):
	"""Owner decision 2026-11-10: the worker host is an IP literal; nothing is resolved."""

	def _refused(self, url):
		with self.assertRaises(WorkerError) as ctx:
			dme.check_worker_url(url)
		return str(ctx.exception)

	def test_ip_literals_pass_without_any_name_resolution(self):
		with mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("resolved")):
			for url in (
				"http://127.0.0.1:8099",
				"http://[::1]:8099",
				"https://127.0.0.1",
				"https://[::1]",
				"https://10.1.2.3:8443",
				"https://192.168.0.5",
				"https://[fd00::5]:8443",
			):
				with self.subTest(url=url):
					dme.check_worker_url(url)

	def test_a_host_name_is_refused_even_when_it_would_resolve_locally(self):
		with mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("resolved")):
			for url in ("http://localhost:8099", "https://worker.internal", "https://worker.example"):
				with self.subTest(url=url):
					self.assertEqual(self._refused(url), "host_not_ip")

	def test_public_ip_and_wrong_ranges_are_refused(self):
		cases = {
			"https://8.8.8.8": "public_address",
			"https://[2001:4860:4860::8888]": "public_address",
			"https://[::ffff:8.8.8.8]": "public_address",  # IPv4-mapped IPv6 judged as IPv4
			"http://10.1.2.3": "http_not_loopback",  # plain http only to loopback
			"http://[fd00::5]": "http_not_loopback",
			"https://169.254.169.254": "bad_address",
			"https://0.0.0.0": "bad_address",
			"https://[fe80::1]": "bad_address",
		}
		for url, reason in cases.items():
			with self.subTest(url=url):
				self.assertEqual(self._refused(url), reason)
		for bad in ("ftp://127.0.0.1", "http://user:pw@127.0.0.1", "http:///x", "http://127.0.0.1:99999"):
			with self.subTest(url=bad):
				self.assertEqual(self._refused(bad), "bad_url")

	def test_a_refused_address_stops_the_job_before_any_photo_and_is_logged_once(self):
		dme._cache().delete_value("card_meter_worker_url_refused:host_not_ip")
		title = frappe._("CARD meter extraction: worker address refused")
		frappe.db.delete("Error Log", {"method": title})
		with (
			mock.patch.object(dme, "worker_config", return_value=("http://localhost:8099", "secret-token")),
			mock.patch.object(dme, "call_worker", side_effect=AssertionError("called")),
			mock.patch.object(dme, "note_failure", side_effect=AssertionError("counted")),
		):
			self.assertEqual(dme.run_extraction("any-fill"), "bad_config")
			self.assertEqual(dme.run_extraction("any-fill"), "bad_config")
		logs = frappe.get_all("Error Log", filters={"method": title}, fields=["error"], limit_page_length=0)
		self.assertEqual(len(logs), 1)  # once per reason and day
		self.assertIn("host_not_ip", logs[0].error)
		self.assertNotIn("localhost", logs[0].error)  # the URL is never logged
		self.assertNotIn("secret-token", logs[0].error)

	def test_worker_off_without_config(self):
		with mock.patch.object(frappe, "conf", frappe._dict()):
			self.assertIsNone(dme.worker_config())
		with mock.patch.object(
			frappe,
			"conf",
			frappe._dict(card_meter_worker_url="http://127.0.0.1:1", card_meter_worker_token="t"),
		):
			self.assertEqual(dme.worker_config(), ("http://127.0.0.1:1", "t"))


class TestDecide(IntegrationTestCase):
	def sides(self, opening, closing):
		return {"opening": opening, "closing": closing}

	def test_r3_clear_pair_writes_only_the_closing_reading(self):
		out = decide(self.sides(reading("00000", side="opening"), reading("00042")), FILL)
		self.assertEqual(out["write"], {"closing_reading": 42.0})
		self.assertEqual(out["needs_review"], False)  # the audit line below is informational: it never routes
		self.assertEqual(list(out["lines"]), ["closing"])
		self.assertIn(
			"Meter reading (closing): 00042; written by meter extraction; check against the photo",
			out["lines"]["closing"],
		)

	def test_ac3_ambiguity_never_writes_a_float(self):
		out = decide(
			self.sides(
				reading("00000", side="opening"), reading("0004?", between=(4,), flags=("half_roll",))
			),
			FILL,
		)
		self.assertEqual(out["write"], {})
		self.assertIn("0004?", out["lines"]["closing"])
		self.assertIn("between 42 and 43 L", out["lines"]["closing"])
		self.assertTrue(
			out["needs_review"]
		)  # Owner rule 2026-11-03: any ambiguous closing goes to review (was OQ-A: not material)

	def test_r5_material_when_litres_are_outside_the_interval(self):
		out = decide(
			self.sides(reading("00000", side="opening"), reading("0004?", between=(4,))),
			dict(FILL, litres=300),
		)
		self.assertEqual(out["write"], {})
		self.assertTrue(out["needs_review"])

	def test_invoice_outside_the_interval_is_material(self):
		out = decide(
			self.sides(None, reading("0004?", between=(4,))), dict(FILL, litres=41, invoiced_litres=500)
		)
		self.assertTrue(out["needs_review"])

	def test_ac6_reset_not_zero_goes_to_review_without_a_float(self):
		out = decide(self.sides(reading("00007", side="opening"), reading("00042")), FILL)
		self.assertEqual(out["write"], {})
		self.assertTrue(out["needs_review"])
		self.assertIn("not reset", out["lines"]["opening"])

	def test_ac7_closing_not_above_opening(self):
		out = decide(self.sides(reading("00000", side="opening"), reading("00000")), FILL)
		self.assertEqual(out["write"], {})
		self.assertTrue(out["needs_review"])

	def test_ac8_entered_litres_that_disagree_are_never_changed(self):
		far = decide(self.sides(reading("00000", side="opening"), reading("00380")), dict(FILL, litres=400))
		self.assertEqual(far["write"], {})
		self.assertTrue(far["needs_review"])
		self.assertIn("entered litres 400", far["lines"]["closing"])
		near = decide(
			self.sides(reading("00000", side="opening"), reading("00401")), dict(FILL, litres=400.5)
		)
		self.assertEqual(near["write"], {})  # 0.5 L apart: not equal to the third decimal, so no write
		self.assertTrue(
			near["needs_review"]
		)  # Owner rule 2026-11-03: a clear reading that was not written goes to review

	def test_ac9_an_entered_reading_is_never_overwritten(self):
		out = decide(
			self.sides(reading("00000", side="opening"), reading("00042")), dict(FILL, closing_reading=50)
		)
		self.assertEqual(out["write"], {})
		self.assertTrue(out["needs_review"])  # contradicts the entry
		same = decide(
			self.sides(reading("00000", side="opening"), reading("00042")), dict(FILL, closing_reading=42)
		)
		self.assertEqual(
			(same["write"], same["needs_review"], same["outcome"]["closing"]), ({}, False, "confirmed")
		)

	def test_r1_r2_unreadable_and_no_meter(self):
		m = meta()
		unread = validate_response(answer(m, status="unreadable"), m, [800, 600])
		out = decide(self.sides(None, unread), FILL)
		self.assertEqual(
			(out["needs_review"], out["outcome"]),
			(True, {"closing": "unreadable"}),  # Owner rule 2026-11-03
		)
		self.assertIn("not readable", out["lines"]["closing"])
		m = meta()
		nometer = validate_response(answer(m, status="no_meter"), m, [800, 600])
		out = decide(self.sides(None, nometer), FILL)
		self.assertTrue(out["needs_review"])
		self.assertIn("no single meter", out["lines"]["closing"])

	def test_drum_count_mismatch_between_photos_is_not_written(self):
		out = decide(self.sides(reading("000000", side="opening"), reading("00042")), FILL)
		self.assertEqual(out["write"], {})
		self.assertIn("drum counts differ", out["lines"]["closing"])
		self.assertTrue(
			out["needs_review"]
		)  # Owner rule 2026-11-03 supersedes M1: the note stays informational but it now routes to review

	def test_owner_rule_path_1_unreadable_side_routes_with_a_visible_line(self):
		m = meta()
		for side in ("opening", "closing"):
			unread = validate_response(answer(m, status="unreadable"), m, [800, 600])
			out = decide({"opening": None, "closing": None, side: unread}, FILL)
			self.assertEqual(
				(out["needs_review"], out["outcome"], out["write"]), (True, {side: "unreadable"}, {})
			)
			self.assertIn(f"Meter reading ({side}): not readable", out["lines"][side])

	def test_owner_rule_path_2_ambiguous_closing_without_a_material_reason_routes(self):
		out = decide(self.sides(None, reading("0004?", between=(4,))), dict(FILL, litres=42))
		self.assertEqual(
			(out["needs_review"], out["write"], out["outcome"]), (True, {}, {"closing": "ambiguous"})
		)
		self.assertIn("0004?", out["lines"]["closing"])
		drums = decide(
			self.sides(reading("000000", side="opening"), reading("00042")), FILL
		)  # drum-count difference only (M1)
		self.assertEqual((drums["needs_review"], drums["write"]), (True, {}))
		self.assertIn("drum counts differ", drums["lines"]["closing"])

	def test_owner_rule_path_3_clear_but_not_written_within_tolerance_routes(self):
		out = decide(self.sides(reading("00000", side="opening"), reading("00401")), dict(FILL, litres=400.5))
		self.assertEqual(
			(out["needs_review"], out["write"], out["outcome"]["closing"]), (True, {}, "clear_not_written")
		)
		self.assertIn("entered litres 400.5", out["lines"]["closing"])

	def test_owner_rule_path_4_entered_closing_ambiguous_inside_the_interval_routes(self):
		out = decide(self.sides(None, reading("0004?", between=(4,))), dict(FILL, closing_reading=42))
		self.assertEqual(
			(out["needs_review"], out["write"], out["outcome"]["closing"]), (True, {}, "ambiguous")
		)
		self.assertIn("entered closing reading 42", out["lines"]["closing"])

	def test_owner_rule_path_5_ambiguous_opening_routes_with_a_line(self):
		out = decide(self.sides(reading("0000?", side="opening", between=(4,)), None), FILL)
		self.assertEqual(
			(out["needs_review"], out["write"], out["outcome"]), (True, {}, {"opening": "ambiguous"})
		)
		self.assertIn("0000?", out["lines"]["opening"])

	def test_owner_rule_clear_written_and_confirmed_stay_draft(self):
		written = decide(self.sides(reading("00000", side="opening"), reading("00042")), FILL)
		self.assertEqual((written["needs_review"], written["outcome"]["closing"]), (False, "clear_written"))
		confirmed = decide(
			self.sides(reading("00000", side="opening"), reading("00042")), dict(FILL, closing_reading=42)
		)
		self.assertEqual((confirmed["needs_review"], confirmed["outcome"]["closing"]), (False, "confirmed"))
		opening_only = decide(self.sides(reading("00000", side="opening"), None), FILL)
		self.assertEqual(
			(opening_only["needs_review"], opening_only["outcome"]), (False, {"opening": "clear_zero"})
		)

	def test_ac13_never_touches_approved_rejected_or_submitted(self):
		for change in (
			{"review_status": "Operations Approved"},
			{"review_status": "Rejected"},
			{"docstatus": 1},
			{"docstatus": 2},
		):
			with self.subTest(change=change):
				out = decide(
					self.sides(reading("00000", side="opening"), reading("00042")), dict(FILL, **change)
				)
				self.assertEqual(
					(out["write"], out["lines"], out["needs_review"], out["outcome"]), ({}, {}, False, {})
				)

	def test_b1_entered_opening_conflict_blocks_the_write(self):
		pair = self.sides(reading("00000", side="opening"), reading("00042"))
		out = decide(pair, dict(FILL, opening_reading=5))
		self.assertEqual(out["write"], {})
		self.assertTrue(out["needs_review"])
		self.assertIn("entered opening reading 5", out["lines"]["opening"])
		same = decide(
			self.sides(reading("00005", side="opening"), reading("00042")), dict(FILL, opening_reading=5)
		)
		self.assertEqual(same["write"], {})  # reset not zero is still escalated

	def test_b2_c1_c2_other_evidence_can_only_escalate_a_clear_pair(self):
		pair = self.sides(reading("00000", side="opening"), reading("00042"))
		for extra in (
			{"invoiced_litres": 400},
			{"messages": "delivered 400 L"},
			{"messages": "سلمنا ٤٠٠ لتر"},
			{"totalizer_window": (100, 110)},
		):
			with self.subTest(extra=extra):
				out = decide(pair, dict(FILL, **extra))
				self.assertEqual(out["write"], {})
				self.assertTrue(out["needs_review"])
		for extra in (
			{"invoiced_litres": 42},
			{"messages": "42 L"},
			{"totalizer_window": (41, 43)},
			{"messages": "no number"},
		):
			with self.subTest(agree=extra):
				out = decide(pair, dict(FILL, **extra))
				self.assertEqual(
					out["write"], {"closing_reading": 42.0}
				)  # agreement does not verify, it only does not escalate

	def test_f2_the_ambiguous_line_names_what_escalates_it(self):
		# opening 6 drums vs closing 5: the drum-count note stays informational; the invoice is what escalates
		pair = self.sides(reading("000000", side="opening"), reading("0004?", between=(4,)))
		out = decide(pair, dict(FILL, litres=42, invoiced_litres=400))
		self.assertTrue(out["needs_review"])
		self.assertIn("drum counts differ", out["lines"]["closing"])
		self.assertIn("invoiced litres 400 differ", out["lines"]["closing"])
		# entered litres outside the interval, a quoted quantity, and nothing escalating at all
		far = decide(self.sides(None, reading("0004?", between=(4,))), dict(FILL, litres=300))
		self.assertTrue(far["needs_review"])
		self.assertIn("entered litres 300 outside the interval", far["lines"]["closing"])
		quoted = decide(
			self.sides(None, reading("0004?", between=(4,))), dict(FILL, messages="delivered 400 L")
		)
		self.assertTrue(quoted["needs_review"])
		self.assertIn("source messages", quoted["lines"]["closing"])
		calm = decide(pair, dict(FILL, litres=42))
		self.assertTrue(calm["needs_review"])  # Owner rule 2026-11-03: the drum-count note alone now routes
		self.assertIn("drum counts differ", calm["lines"]["closing"])
		self.assertNotIn("outside the interval", calm["lines"]["closing"])
		self.assertNotIn("invoiced", calm["lines"]["closing"])

	def test_quoted_litres_parsing(self):
		self.assertEqual(
			dme.quoted_litres("got 400 L and 12.5 liters, ٣٠ لتر, price 5 SAR"), [400.0, 12.5, 30.0]
		)
		self.assertEqual(dme.quoted_litres(None), [])

	def test_split_block_and_crop_limits(self):
		text = "Hello\nMeter reading (closing): 0004? (between 40 and 41 L)\nMeter reading (opening): 00000"
		self.assertEqual(sorted(dme.split_block(text)), ["closing", "opening"])

	@staticmethod
	def _jpeg(width, height):
		import io

		from PIL import Image

		out = io.BytesIO()
		Image.new("RGB", (width, height), (40, 90, 140)).save(out, "JPEG")
		return out.getvalue()

	@staticmethod
	def _size(data):
		import io

		from PIL import Image

		with Image.open(io.BytesIO(data)) as im:
			return im.size

	def test_a_close_up_meter_box_still_gets_a_crop(self):
		# T0050: a 1033 px wide box in a 1600 px photo (65% of the width) used to be refused silently; width alone never refuses
		image = self._jpeg(1600, 1200)
		data = dme.make_crop(image, [280, 300, 1033, 300], [1600, 1200])
		self.assertIsNotNone(data)
		mx, my = (
			1033 * dme.CROP_MARGIN,
			300 * dme.CROP_MARGIN,
		)  # the box plus the fixed margin, truncated like the code does
		self.assertEqual(
			self._size(data), (int(280 + 1033 + mx) - int(280 - mx), int(300 + 300 + my) - int(300 - my))
		)
		self.assertIsNotNone(
			dme.make_crop(image, [100, 100, 879, 250], [1600, 1200])
		)  # an 879 px wide closing box
		self.assertIsNotNone(
			dme.make_crop(image, [0, 0, 1600, 300], [1600, 1200])
		)  # as wide as the frame but short: a counter row

	def test_a_full_frame_a_tall_or_an_invalid_box_gives_no_crop(self):
		image = self._jpeg(1600, 1200)
		for box in (
			[0, 0, 1600, 1200],  # the whole frame
			[10, 10, 1560, 1170],  # essentially the whole frame
			[100, 100, 500, 840],  # 70% of the height
			[100, 100, 0, 50],  # no width
			[100, 100, 50, -5],  # negative height
		):
			with self.subTest(box=box):
				self.assertIsNone(dme.make_crop(image, box, [1600, 1200]))

	def test_the_60_percent_limits_are_exact(self):
		image = self._jpeg(1600, 1200)
		self.assertIsNotNone(
			dme.make_crop(image, [0, 0, 1600, 720], [1600, 1200])
		)  # area and height exactly 60%
		self.assertIsNone(dme.make_crop(image, [0, 0, 1600, 721], [1600, 1200]))  # height just over 60%

	def test_a_box_partly_outside_the_image_is_clamped(self):
		data = dme.make_crop(self._jpeg(800, 600), [700, 500, 300, 200], [800, 600])
		self.assertIsNotNone(data)
		width, height = self._size(data)
		self.assertTrue(0 < width <= 800 and 0 < height <= 600)
		self.assertEqual(
			(width, height), (800 - int(700 - 300 * dme.CROP_MARGIN), 600 - int(500 - 200 * dme.CROP_MARGIN))
		)
		self.assertIsNone(
			dme.make_crop(self._jpeg(800, 600), [900, 700, 50, 50], [800, 600])
		)  # nothing left after clamping


class TestFillIntegration(IntegrationTestCase):
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
		_set("diesel_price_exception_role", "Accounts Manager")
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-DME-PRJ-" + self.token
		proj.company = self.company
		self.project = proj.insert(ignore_permissions=True).name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DME-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		self.supplier = sup.insert(ignore_permissions=True).name
		set_diesel_price(self.company, 1.79)
		self.user = _role_user("Card User")
		self.cfg = mock.patch.object(dme, "worker_config", return_value=("http://127.0.0.1:9", "t"))
		self.cfg.start()

	def tearDown(self):
		self.cfg.stop()
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- helpers ----------
	def _photo(self, temp, field):
		return (
			frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"meter-{frappe.generate_hash(length=10)}.png",
					"is_private": 1,
					"content": png(frappe.generate_hash(length=32)),
					"attached_to_doctype": "Project Diesel Fill",
					"attached_to_name": temp,
					"attached_to_field": field,
				}
			)
			.insert(ignore_permissions=True)
			.file_url
		)

	def _fill(self, litres=42, with_enqueue=False, enqueue_error=None, **extra):
		temp = "new-project-diesel-fill-" + frappe.generate_hash(length=8)
		doc = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-08-25",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": litres,
				"opening_photo": self._photo(temp, "opening_photo"),
				"closing_photo": self._photo(temp, "closing_photo"),
				**extra,
			}
		)
		setattr(doc, "__temporary_name", temp)
		if {"source_messages", "invoiced_litres"} & set(extra):
			doc.flags.diesel_import = True  # these fields are set by the session import only
		with mock.patch("frappe.enqueue", side_effect=enqueue_error) as enq:
			doc.insert()
		self.enqueued = enq
		return doc

	def _worker(self, opening="00000", closing="00042", **kw):
		"""A mocked transport answering per side from the request meta; records the calls."""
		self.calls = []
		texts = {"opening": opening, "closing": closing}

		def post(url, token, m, image, ctype):
			self.calls.append(m["side"])
			text = texts[m["side"]]
			size = dme.image_size_of(image)
			between = (len(text.replace(".", "")) - 1,) if "?" in text and kw.get("between") else ()
			body = answer(
				m,
				text,
				between=between,
				size=tuple(size),
				box=(0, 0, size[0], size[1])
				if kw.get("full_frame")
				else (1, 1, max(2, size[0] // 3), max(2, size[1] // 6)),
			)
			return 200, "application/json", json.dumps(body).encode()

		return mock.patch.object(dme, "_post", side_effect=post)

	def _run(self, fill, user=None):
		frappe.set_user(user or self.user)
		try:
			with mock.patch("frappe.enqueue"):
				self.status = dme.run_extraction(fill.name)
		finally:
			frappe.set_user("Administrator")
		return frappe.get_doc("Project Diesel Fill", fill.name)

	def _markers(self, fill):
		return frappe.get_all(
			"Comment",
			filters={
				"reference_name": fill.name,
				"comment_type": "Info",
				"content": ["like", dme.MARKER_PREFIX + "%"],
			},
			pluck="content",
		)

	def _crops(self, fill):
		return frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Project Diesel Fill",
				"attached_to_name": fill.name,
				"file_name": ["like", "meter-crop-%"],
			},
			fields=["file_name", "is_private"],
		)

	# ---------- AC-1, AC-2, AC-14, AC-17, AC-18 ----------
	def test_clear_pair_completes_the_draft_once(self):
		fill = self._fill(litres=42)
		originals = (fill.opening_photo, fill.closing_photo)
		with self._worker():
			after = self._run(fill)
			self.assertEqual(self.status, "applied")
			self.assertEqual((flt(after.closing_reading), flt(after.litres)), (42, 42))
			self.assertEqual((after.review_status, after.docstatus), ("Draft", 0))
			# audit trail: the machine-written number keeps an informational line and the fill stays a Draft
			self.assertIn("written by meter extraction; check against the photo", after.evidence_warnings)
			self.assertNotIn("Needs Review", after.review_status)
			after.remarks = "edited by a person"
			after.save()  # an unrelated save keeps the line
			self.assertIn(
				"Meter reading (closing)", frappe.get_doc(fill.doctype, fill.name).evidence_warnings
			)
			self.assertEqual(len(self._markers(fill)), 2)
			self.assertTrue(self._crops(fill) and all(c.is_private for c in self._crops(fill)))
			self.assertEqual((after.opening_photo, after.closing_photo), originals)
			versions = frappe.db.count("Version", {"docname": fill.name})
			again = self._run(fill)  # same photo bytes: no worker call, no new marker, crop or version
			self.assertEqual(sorted(self.calls), ["closing", "opening"])
			self.assertEqual(len(self._markers(fill)), 2)
			self.assertEqual(frappe.db.count("Version", {"docname": fill.name}), versions)
			self.assertEqual(flt(again.closing_reading), 42)

	def test_a_refused_crop_writes_no_file_but_the_marker_is_still_written(self):
		fill = self._fill(litres=42)
		with self._worker(full_frame=True):  # the worker boxes the whole frame: not a counter crop
			after = self._run(fill)
		self.assertEqual(self.status, "applied")
		self.assertEqual(flt(after.closing_reading), 42)  # the reading itself is unaffected
		self.assertEqual(self._crops(fill), [])
		self.assertEqual(len(self._markers(fill)), 2)

	def test_photo_bytes_come_raw_from_the_file_api_and_a_decoded_str_is_refused(self):
		fill = self._fill(litres=42)
		get_content = "frappe.core.doctype.file.file.File.get_content"
		data, content_type = dme._photo_bytes(fill, "opening_photo")  # the real read: raw bytes
		self.assertTrue(isinstance(data, bytes) and content_type == "image/png")
		with mock.patch(get_content, return_value="decoded text") as read:
			with self.assertRaises(WorkerError) as refused:
				dme._photo_bytes(fill, "opening_photo")
		self.assertEqual(str(refused.exception), "not_bytes")
		self.assertEqual(read.call_args.kwargs, {"encodings": ()})

	def test_nothing_is_submitted_or_posted(self):
		fill = self._fill(litres=42)
		with self._worker():
			after = self._run(fill)
		self.assertEqual(after.docstatus, 0)
		self.assertFalse(after.purchase_invoice)

	# ---------- AC-3, AC-4, AC-5: ambiguity ----------
	def test_ambiguous_closing_is_recorded_not_written_and_survives_a_save(self):
		fill = self._fill(litres=42)
		with self._worker(closing="0004?", between=True):
			after = self._run(fill)
		self.assertEqual(self.status, "applied")
		self.assertEqual(flt(after.closing_reading), 0)
		self.assertIn("Meter reading (closing): 0004?", after.evidence_warnings)
		self.assertEqual(
			after.review_status, "Needs Review"
		)  # Owner rule 2026-11-03: ambiguous always goes to review
		after.remarks = "edited by a person"
		after.save()
		self.assertIn(
			"Meter reading (closing): 0004?", frappe.get_doc(fill.doctype, fill.name).evidence_warnings
		)

	def test_material_ambiguity_goes_to_needs_review(self):
		fill = self._fill(litres=900)
		with self._worker(closing="0004?", between=True):
			after = self._run(fill)
		self.assertEqual(after.review_status, "Needs Review")
		self.assertEqual(flt(after.closing_reading), 0)

	def test_a_persons_correction_ends_the_dispute_and_keeps_one_record(self):
		fill = self._fill(litres=900)
		with self._worker(closing="0004?", between=True):
			after = self._run(fill)
		after.closing_reading = 900
		after.save()
		after = frappe.get_doc(fill.doctype, fill.name)
		self.assertNotIn("Meter reading (closing)", after.evidence_warnings or "")
		self.assertEqual(frappe.db.count("Project Diesel Fill", {"project": self.project}), 1)

	# ---------- AC-9, AC-13, no-op rules ----------
	def test_entered_closing_reading_is_not_overwritten(self):
		fill = self._fill(litres=50, closing_reading=50)
		with self._worker(closing="00042"):
			after = self._run(fill)
		self.assertEqual(flt(after.closing_reading), 50)
		self.assertEqual(after.review_status, "Needs Review")

	def test_operations_approved_fill_is_untouched(self):
		fill = self._fill(litres=42)
		frappe.db.set_value("Project Diesel Fill", fill.name, "review_status", "Operations Approved")
		with self._worker():
			self._run(fill)
		self.assertEqual(self.calls, [])
		self.assertEqual(self._markers(fill), [])

	def test_job_without_a_user_writes_nothing(self):
		fill = self._fill(litres=42)
		with self._worker():
			frappe.set_user("Guest")
			try:
				dme.run_extraction(fill.name)
			finally:
				frappe.set_user("Administrator")
		self.assertEqual((self.calls, self._markers(fill)), ([], []))
		self.assertEqual(flt(frappe.db.get_value(fill.doctype, fill.name, "closing_reading")), 0)

	def test_user_without_write_permission_changes_nothing(self):
		fill = self._fill(litres=42)
		with self._worker():
			self._run(fill, user=_role_user("Employee"))
		self.assertEqual(self.calls, [])

	# ---------- R0: the worker fails ----------
	def test_worker_failure_changes_nothing_and_the_third_failure_leaves_one_marker(self):
		fill = self._fill(litres=42)
		with mock.patch.object(dme, "_post", side_effect=OSError("down")):
			for _ in range(3):
				after = self._run(fill)
		self.assertEqual((flt(after.closing_reading), after.review_status), (0, "Draft"))
		self.assertEqual(self._markers(fill), [])  # M2: a connection error is retry-later, never counted
		with mock.patch.object(dme, "_post", side_effect=OSError("down")) as post:
			self._run(fill)
			post.assert_called()  # still retried: transient errors do not exhaust the cap

	# ---------- trigger ----------
	def test_new_photo_enqueues_one_job_and_worker_off_enqueues_none(self):
		self._fill()
		self.enqueued.assert_called_once()
		kwargs = self.enqueued.call_args.kwargs
		self.assertEqual((kwargs["queue"], kwargs["enqueue_after_commit"]), ("long", True))
		with mock.patch.object(dme, "worker_config", return_value=None):
			self._fill()
			self.enqueued.assert_not_called()

	def test_h1_a_failing_enqueue_never_fails_the_save(self):
		from redis.exceptions import ConnectionError as RedisConnectionError

		for error in (
			frappe.QueueOverloaded("full"),
			RedisConnectionError("redis down"),
			ConnectionError("down"),
			RuntimeError("odd"),
		):
			with self.subTest(error=type(error).__name__):
				logs = frappe.db.count("Error Log", {"method": "CARD meter extraction: enqueue skipped"})
				fill = self._fill(litres=42, enqueue_error=error)  # the save (insert) must succeed
				self.assertTrue(frappe.db.exists("Project Diesel Fill", fill.name))
				self.enqueued.assert_called_once()
				self.assertEqual(self._markers(fill), [])  # no marker, nothing written, nothing retried
				self.assertEqual(self._crops(fill), [])
				self.assertEqual(
					flt(frappe.db.get_value("Project Diesel Fill", fill.name, "closing_reading")), 0
				)
				self.assertEqual(
					frappe.db.count("Error Log", {"method": "CARD meter extraction: enqueue skipped"}),
					logs + 1,
				)
				row = frappe.get_all(
					"Error Log",
					filters={"method": "CARD meter extraction: enqueue skipped", "reference_name": fill.name},
					fields=["error"],
					limit=1,
				)
				self.assertTrue(
					row and type(error).__name__ in row[0].error
				)  # the exception type only: no image data

	def test_a_saved_fill_without_photo_changes_does_not_enqueue(self):
		fill = self._fill()
		fill.remarks = "x"
		with mock.patch("frappe.enqueue") as enq:
			fill.save()
		enq.assert_not_called()

	# ---------- T0045: accounting B-1/B-2/C-1/C-2, security F2, contract M2/M3/L2 ----------
	def test_b1_a_person_entered_opening_never_changes_the_litres(self):
		fill = self._fill(
			litres=42, opening_reading=5
		)  # litres 42 entered with an opening of 5 and no closing
		with self._worker(opening="00000", closing="00042"):
			after = self._run(fill)
		self.assertEqual(self.status, "applied")
		self.assertEqual((flt(after.litres), flt(after.closing_reading)), (42, 0))
		self.assertEqual(after.review_status, "Needs Review")
		self.assertIn("entered opening reading 5", after.evidence_warnings)

	def test_b2_a_clear_pair_that_contradicts_the_invoice_is_escalated_not_written(self):
		fill = self._fill(litres=42, invoiced_litres=400)
		with self._worker():
			after = self._run(fill)
		self.assertEqual((flt(after.closing_reading), after.review_status), (0, "Needs Review"))
		self.assertIn("invoiced litres 400 differ", after.evidence_warnings)

	def test_c1_a_quantity_quoted_in_the_messages_can_only_escalate(self):
		fill = self._fill(litres=42, source_messages="Ibrahim: delivered 400 L today")
		with self._worker():
			after = self._run(fill)
		self.assertEqual((flt(after.closing_reading), after.review_status), (0, "Needs Review"))
		agree = self._fill(litres=42, source_messages="Ibrahim: 42 L done")
		with self._worker():
			done = self._run(agree)
		self.assertEqual(flt(done.closing_reading), 42)  # agreement never verifies, it just does not escalate

	def test_c2_the_totalizer_is_checked_before_the_float_is_written(self):
		fill = self._fill(litres=42, opening_totalizer="0000000", closing_totalizer="0000100")
		with self._worker():
			after = self._run(fill)
		self.assertEqual((flt(after.closing_reading), after.review_status), (0, "Needs Review"))
		self.assertIn("totalizer moved", after.evidence_warnings)

	def test_f2_a_forged_marker_comment_is_ignored_and_a_signed_one_is_trusted(self):
		fill = self._fill(litres=42)
		sha = "d" * 64
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": "Project Diesel Fill",
				"reference_name": fill.name,
				"content": f"{dme.marker_prefix('opening', sha)}1.0 m=bbbbbbbbbbbb: clear_zero #0123456789abcdef",
			}
		).insert(ignore_permissions=True)
		self.assertIsNone(dme.find_marker(fill.name, "opening", sha))
		dme.add_marker(fill, "opening", sha, {"version": "1.0", "models": "bbbbbbbbbbbb"}, "clear_zero")
		self.assertEqual(dme.find_marker(fill.name, "opening", sha), "clear_zero")
		self.assertTrue(  # L2: the models hash prefix is in the signed marker
			any(
				"m=bbbbbbbbbbbb: clear_zero #" in m and "0123456789abcdef" not in m
				for m in self._markers(fill)
			)
		)

	def test_m2_invalid_answers_count_toward_the_cap_and_busy_ones_do_not(self):
		fill = self._fill(litres=42)
		bad = mock.patch.object(dme, "_post", return_value=(200, "application/json", b"not json"))
		with bad:
			for _ in range(3):
				self._run(fill)
		self.assertTrue(any("worker_error" in m for m in self._markers(fill)))
		with mock.patch.object(dme, "_post", return_value=(200, "application/json", b"not json")) as post:
			self._run(fill)
			post.assert_not_called()  # cap reached for these photo bytes
		other = self._fill(litres=42)
		with mock.patch.object(dme, "_post", return_value=(429, "application/json", b"{}")) as post:
			for _ in range(4):
				self._run(other)
			self.assertEqual(post.call_count, 8)  # two photos x four runs: 429 is never counted
		self.assertEqual(self._markers(other), [])

	def test_m2_jobs_for_one_fill_are_serialised_by_a_lock(self):
		fill = self._fill(litres=42)
		with mock.patch("frappe.utils.synchronization.filelock") as lock, self._worker():
			self._run(fill)
		self.assertIn(fill.name, lock.call_args.args[0])

	def test_m3_the_http_client_ignores_proxy_environment_variables(self):
		made = []

		class FakeResponse:
			def __init__(self):
				self.status_code = 200
				self.headers = {"Content-Type": "application/json"}
				self.raw = mock.Mock(read=lambda *a, **k: b"{}")

			def __enter__(self):
				return self

			def __exit__(self, *a):
				return False

		class FakeSession:
			def __init__(self):
				made.append(self)
				self.trust_env = True
				self.proxies = {"https": "http://proxy.invalid:3128"}

			def post(self, *a, **k):
				return FakeResponse()

			def close(self):
				pass

		with mock.patch("requests.Session", FakeSession), mock.patch.object(dme, "check_worker_url"):
			dme._post("http://127.0.0.1:9", "t", {"a": 1}, b"x", "image/png")
		self.assertEqual((made[0].trust_env, made[0].proxies), (False, {}))

	def test_audit_trail_keeps_machine_and_human_values(self):
		fill = self._fill(litres=42)
		with self._worker():
			after = self._run(fill)
		# Frappe's Document._save sets ignore_version = frappe.in_test, so Version rows are not written inside a
		# test run (version-16 source); in production track_changes records the Float change of this very save.
		# What a test can prove: the DocType tracks changes, the machine outcome is in the signed marker Comment.
		self.assertTrue(frappe.get_meta("Project Diesel Fill").track_changes)
		self.assertTrue(any("clear_written" in m for m in self._markers(fill)))
		self.assertEqual(flt(after.closing_reading), 42)
