# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Meter-reading extraction inside the existing Project Diesel Fill (Owner decision 2026-11-02).

An OPTIONAL local worker reads the meter photos. CARD treats everything the worker returns as untrusted data: it
validates it (`validate_response`), decides what it may do (`decide`, a pure function: the decision table of
docs/card/ocr-real/METER_WORKER_CONTRACT.md section 5) and hands the validated result to the fill's own `validate()`
(`ProjectDieselFill._apply_meter_extraction`) through `doc.flags.meter_extraction`. No new field, DocType or Python
dependency; no `ignore_permissions`; no submit, no GL. The worker is configured only in site_config
(`card_meter_worker_url`, `card_meter_worker_token`); absent = today's manual flow, unchanged.

Flow: fill saved with a new/changed photo -> `after_fill_saved` (on_update) enqueues `run_extraction` -> the job, running
as the saving user, reads the private photo, calls the worker, validates, then `doc.save()` -> `validate()` applies the
decision -> `after_fill_saved` writes the marker Comment and the private crop File.
"""

import hashlib
import hmac
import io
import ipaddress
import json
import os
import re
import socket
import uuid
from urllib.parse import urlparse

import frappe
from frappe.utils import cstr, flt, get_datetime

CONTRACT_VERSION = "1.0"
SIDES = ("opening", "closing")
PHOTO_FIELD = {"opening": "opening_photo", "closing": "closing_photo"}
LINE_PREFIX = "Meter reading ({0}):"
MARKER_PREFIX = "Meter extraction"
TOLERANCE = 1  # litres: the existing TOTALIZER_READ_TOLERANCE (no new threshold without the Owner)
EXACT = 0.001  # a written reading must equal the litres a person entered, to the third decimal
MAX_RESPONSE = 64 * 1024
CROP_MARGIN = 0.04
MAX_ATTEMPTS = 3
EDITABLE = (None, "", "Draft", "Needs Review")
STATUSES = ("ok", "no_meter", "unreadable", "error")
DRUM_STATES = ("clear", "between", "unreadable")
FLAGS = (
	"glare",
	"blur",
	"skew",
	"low_res",
	"shadow",
	"window_cut",
	"half_roll",
	"polarity_unclear",
	"drum_count_unexpected",
	"not_a_meter",
	"multiple_meters",
	"overlay_unreadable",
	"carry_inconsistent",
)
DEFECT_FLAGS = frozenset(
	(
		"not_a_meter",
		"multiple_meters",
		"drum_count_unexpected",
		"window_cut",
		"polarity_unclear",
		"carry_inconsistent",
	)
)
READING_RE = re.compile(r"^[0-9?]{1,9}(\.[0-9?])?$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")  # no leading dot, no ".." (checked below), no "/"
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,23}$")
MAX_PHOTO_BYTES = 10 * 1024 * 1024  # the same cap as the attachment validator
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class WorkerError(Exception):
	"""Anything wrong with the worker or its answer: handled as 'worker unavailable for this photo' (R0).
	`transient` errors (busy, unavailable, connection) are retry-later and do not count toward the attempt cap."""

	TRANSIENT = frozenset(("transport", "unresolved", "http_429", "http_503"))

	@property
	def transient(self):
		return str(self) in self.TRANSIENT


# ------------------------------------------------------------------ configuration and transport
def worker_config():
	"""(url, token) from site_config, or None when the feature is off."""
	url, token = frappe.conf.get("card_meter_worker_url"), frappe.conf.get("card_meter_worker_token")
	return (cstr(url).rstrip("/"), cstr(token)) if url and token else None


def check_worker_url(url):
	"""SSRF guard: http only to a loopback address, https only to loopback or private ranges."""
	parts = urlparse(url)
	if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
		raise WorkerError("bad_url")
	try:
		infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
	except OSError:
		raise WorkerError("unresolved")
	for info in infos:
		ip = ipaddress.ip_address(info[4][0])
		if ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
			raise WorkerError("bad_address")
		if parts.scheme == "http" and not ip.is_loopback:
			raise WorkerError("http_not_loopback")
		if not (ip.is_loopback or ip.is_private):
			raise WorkerError("public_address")


def _post(url, token, meta, image, content_type):
	"""One bounded HTTP call -> (status code, content type, body bytes). Separate so tests replace it."""
	import requests

	check_worker_url(url)
	files = {"meta": (None, json.dumps(meta), "application/json"), "image": ("image", image, content_type)}
	headers = {"Authorization": f"Bearer {token}", "X-Contract-Version": CONTRACT_VERSION}
	session = requests.Session()
	session.trust_env = False  # M3: no HTTP(S)_PROXY / NO_PROXY / netrc from the process environment
	session.proxies = {}
	try:
		with session.post(
			url + "/v1/meter/extract",
			headers=headers,
			files=files,
			timeout=(3, 30),
			allow_redirects=False,
			stream=True,
		) as r:
			body = r.raw.read(MAX_RESPONSE + 1, decode_content=True)
			return r.status_code, r.headers.get("Content-Type", ""), body
	finally:
		session.close()


def image_size_of(content):
	from PIL import Image

	with Image.open(io.BytesIO(content)) as im:
		return [im.width, im.height]


def call_worker(config, side, sha, image, content_type):
	"""Send one photo; returns the validated reading. Raises WorkerError for every failure (R0)."""
	meta = {
		"contract_version": CONTRACT_VERSION,
		"request_id": str(uuid.uuid4()),
		"side": side,
		"photo_sha256": sha,
	}
	try:
		status, ctype, body = _post(config[0], config[1], meta, image, content_type)
	except WorkerError:
		raise
	except Exception:
		raise WorkerError("transport")
	if status != 200:
		raise WorkerError(f"http_{status}")
	if not cstr(ctype).lower().startswith("application/json"):
		raise WorkerError("content_type")
	if len(body) > MAX_RESPONSE:
		raise WorkerError("too_large")
	try:
		data = json.loads(body.decode("utf-8"))
	except (UnicodeDecodeError, ValueError):
		raise WorkerError("not_json")
	return validate_response(data, meta, image_size_of(image))


# ------------------------------------------------------------------ validation of the worker's answer (fail closed)
def _num(v, lo=None):
	if isinstance(v, bool) or not isinstance(v, int | float) or v != v or v in (float("inf"), float("-inf")):
		raise WorkerError("bad_number")
	if lo is not None and v < lo:
		raise WorkerError("number_range")
	return v


def _str(v, limit):
	if not isinstance(v, str) or len(v) > limit:
		raise WorkerError("bad_string")
	return _CTRL.sub("", v)


def validate_response(data, meta, image_size):
	"""Section 4 of the contract. Returns a normalised reading built only from validated values."""
	if not isinstance(data, dict) or data.get("contract_version") != CONTRACT_VERSION:
		raise WorkerError("contract")
	if data.get("request_id") != meta["request_id"] or data.get("photo_sha256") != meta["photo_sha256"]:
		raise WorkerError("echo")
	eng = data.get("engine")
	if not isinstance(eng, dict) or not SHA_RE.match(cstr(eng.get("models_hash"))):
		raise WorkerError("engine")
	# F1 / L1: both go into a Comment, a File name and the evidence text: a strict charset, nothing else
	name, version = eng.get("name"), eng.get("version")
	if not (
		isinstance(name, str)
		and NAME_RE.match(name)
		and isinstance(version, str)
		and VERSION_RE.match(version)
		and ".." not in name + version
	):
		raise WorkerError("engine")
	engine = {"name": name, "version": version, "models": eng["models_hash"][:12]}
	status = data.get("status")
	if status not in STATUSES:
		raise WorkerError("status")
	flags = data.get("flags", [])
	if not isinstance(flags, list) or any(f not in FLAGS for f in flags) or len(set(flags)) != len(flags):
		raise WorkerError("flags")
	if status == "error":
		raise WorkerError("worker_error")
	out = {
		"status": status,
		"flags": list(flags),
		"engine": engine,
		"sha": meta["photo_sha256"],
		"side": meta["side"],
		"image_size": list(image_size),
		"clear": False,
		"value": None,
	}
	if status != "ok":
		return out
	window = data.get("window")
	if (
		not isinstance(window, dict)
		or window.get("found") is not True
		or window.get("image_size") != list(image_size)
	):
		raise WorkerError("window")
	box = window.get("box")
	if not (isinstance(box, list) and len(box) == 4):
		raise WorkerError("box")
	x, y, w, h = [_num(v, 0) for v in box]
	if w <= 0 or h <= 0 or x + w > image_size[0] or y + h > image_size[1]:
		raise WorkerError("box")
	layout, drums, reading = data.get("layout"), data.get("drums"), data.get("reading")
	if not (isinstance(layout, dict) and isinstance(drums, list) and isinstance(reading, dict)):
		raise WorkerError("shape")
	n, dec = layout.get("drum_count"), layout.get("decimal_present")
	if (
		isinstance(n, bool)
		or not isinstance(n, int)
		or not 3 <= n <= 9
		or not isinstance(dec, bool)
		or len(drums) != n
	):
		raise WorkerError("layout")
	text = reading.get("text")
	if (
		not isinstance(text, str)
		or not READING_RE.match(text)
		or ("." in text) != dec
		or (dec and text[-2] != ".")
	):
		raise WorkerError("reading_text")
	chars = text.replace(".", "")
	if len(chars) != n:
		raise WorkerError("reading_length")
	all_clear = True
	for i, d in enumerate(drums):
		if not isinstance(d, dict) or d.get("pos") != i or d.get("state") not in DRUM_STATES:
			raise WorkerError("drum")
		if d["state"] == "clear":
			digit = d.get("digit")
			if (
				isinstance(digit, bool)
				or not isinstance(digit, int)
				or not 0 <= digit <= 9
				or chars[i] != str(digit)
			):
				raise WorkerError("drum_digit")
			continue
		all_clear = False
		if chars[i] != "?":
			raise WorkerError("drum_char")
		if d["state"] == "between":
			for key in ("digit", "digit_next"):
				v = d.get(key)
				if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 9:
					raise WorkerError("between_digits")
	for d in drums:
		if d["state"] == "between" and d["digit_next"] != (d["digit"] + 1) % 10:
			raise WorkerError("between_digits")
	value = reading.get("value")
	low, high = _num(reading.get("interval_low")), _num(reading.get("interval_high"))
	if low > high or (value is None) != ("?" in text):
		raise WorkerError("interval")
	if value is not None and (_num(value) < low or value > high or abs(float(text) - value) > 1e-9):
		raise WorkerError("value")
	# F3: the interval is recomputed from the drums (a half-rolled drum spans one unit of its place, an unreadable one
	# 0-9) and must equal the worker's: a bad worker cannot widen or narrow it to steer the review routing
	exp_low = exp_high = 0.0
	for i, d in enumerate(drums):
		place = 10 ** (n - 1 - i)
		if d["state"] == "clear":
			exp_low += d["digit"] * place
			exp_high += d["digit"] * place
		elif d["state"] == "between":
			exp_low += d["digit"] * place
			exp_high += (d["digit"] + 1) * place
		else:
			exp_high += 9 * place
	div = 10 if dec else 1
	if abs(exp_low / div - low) > 1e-6 or abs(exp_high / div - high) > 1e-6:
		raise WorkerError("interval_recomputed")
	overlay = data.get("overlay")
	if isinstance(overlay, dict) and overlay.get("datetime") is not None:  # L3: optional, but must parse
		try:
			get_datetime(_str(overlay["datetime"], 32))
		except Exception:
			raise WorkerError("overlay_datetime")
	out.update(
		{
			"text": text,
			"value": None if value is None else float(value),
			"low": float(low),
			"high": float(high),
			"drum_count": n,
			"decimal_present": dec,
			"box": [float(x), float(y), float(w), float(h)],
			"clear": all_clear and not (set(flags) & DEFECT_FLAGS),
		}
	)
	return out


# ------------------------------------------------------------------ the decision table (pure)
def _fmt(v):
	return ("%.3f" % v).rstrip("0").rstrip(".")


def _line(side, r, extra=None):
	"""CARD-built text from validated fields only (never the worker's strings)."""
	head = f"{LINE_PREFIX.format(side)} {r['text']}"
	if r["value"] is None:
		head += f" (between {_fmt(r['low'])} and {_fmt(r['high'])} L)"
	parts = [head]
	if r["flags"]:
		parts.append("flags: " + ", ".join(r["flags"]))
	if extra:
		parts.append(extra)
	parts.append(f"extraction {r['engine']['name']} {r['engine']['version']}")
	return "; ".join(parts)


_QUANTITY = re.compile(
	r"(?<![\d.,])(\d{1,6}(?:[.,]\d{1,3})?)\s*(?:liters?|litres?|ltr|l\b|لتر)", re.IGNORECASE
)
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")


def quoted_litres(text):
	"""Quantities in litres quoted in the source messages (heuristic, used only to ESCALATE; never to verify)."""
	out = []
	for m in _QUANTITY.finditer(cstr(text).translate(_ARABIC_DIGITS)):
		try:
			out.append(float(m.group(1).replace(",", ".")))
		except ValueError:
			continue
	return out


def decide(sides, fill):
	"""sides: {"opening": reading|None, "closing": reading|None} (None = not processed now).
	fill: dict(docstatus, review_status, litres, opening_reading, closing_reading, invoiced_litres).
	-> {"write": {field: value}, "lines": {side: text}, "needs_review": bool, "outcome": {side: token}}."""
	res = {"write": {}, "lines": {}, "needs_review": False, "outcome": {}}
	if fill.get("docstatus") != 0 or fill.get("review_status") not in EDITABLE:
		return res  # Operations Approved / Rejected / submitted / cancelled: never touched
	litres, invoiced = flt(fill.get("litres")), flt(fill.get("invoiced_litres"))
	entered_open, entered_close = flt(fill.get("opening_reading")), flt(fill.get("closing_reading"))
	live = {}
	for side in SIDES:
		r = sides.get(side)
		if r is None:
			continue
		if r["status"] == "unreadable":
			res["outcome"][side] = "unreadable"  # R1: manual flow, marker only
		elif r["status"] == "no_meter" or {"multiple_meters", "not_a_meter"} & set(r["flags"]):
			res["outcome"][side] = "no_meter"  # R2: the evidence itself is invalid
			res["lines"][side] = f"{LINE_PREFIX.format(side)} no single meter found in the photo"
			res["needs_review"] = True
		else:
			live[side] = r
	o, c = live.get("opening"), live.get("closing")
	if o and o["clear"] and o["value"] != 0:
		res["outcome"]["opening"] = "reset_not_zero"  # R4 / M3
		res["lines"]["opening"] = _line("opening", o, "the meter was not reset to zero")
		res["needs_review"] = True
	elif o:
		res["outcome"]["opening"] = "clear_zero" if (o["clear"] and o["value"] == 0) else "ambiguous"
		if res["outcome"]["opening"] == "ambiguous":
			res["lines"]["opening"] = _line("opening", o)
	blocked = False
	if (
		entered_open > 0 and o
	):  # B-1: a person-entered opening reading is never replaced or silently contradicted
		if o["clear"]:
			conflict = abs(o["value"] - entered_open) > EXACT
		else:
			conflict = not (o["low"] - TOLERANCE <= entered_open <= o["high"] + TOLERANCE)
		if conflict:
			blocked = True
			res["outcome"]["opening"] = "conflict_entered"
			res["lines"]["opening"] = _line("opening", o, f"entered opening reading {_fmt(entered_open)}")
			res["needs_review"] = True
	if not c:
		return res
	messages = quoted_litres(fill.get("messages"))
	window = fill.get("totalizer_window")

	def cross_checks(lo, hi, exact):
		"""Evidence that can only ESCALATE (never verify): invoice, quantity quoted in the messages and, for an exact
		session, the existing totalizer window (C-2: checked before any Float is written)."""
		why = []
		if invoiced and not (lo - TOLERANCE <= invoiced <= hi + TOLERANCE):
			why.append(f"invoiced litres {_fmt(invoiced)} differ")
		if messages and not any(lo - TOLERANCE <= q <= hi + TOLERANCE for q in messages):
			why.append("a quantity quoted in the source messages differs")
		if exact and window and not (window[0] - TOLERANCE <= lo <= window[1] + TOLERANCE):
			why.append(f"the totalizer moved {_fmt(max(window[0], 0))} to {_fmt(max(window[1], 0))} L")
		return why

	base_lo, base_hi = (o["low"], o["high"]) if o else (entered_open, entered_open)
	if entered_close > 0:  # a person entered it first (never overwritten)
		if c["clear"] and abs(c["value"] - entered_close) <= EXACT:
			res["outcome"]["closing"] = "confirmed"
		else:
			conflict = not (c["low"] - TOLERANCE <= entered_close <= c["high"] + TOLERANCE)
			res["outcome"]["closing"] = "conflict_entered" if conflict else "ambiguous"
			res["lines"]["closing"] = _line("closing", c, f"entered closing reading {_fmt(entered_close)}")
			res["needs_review"] = res["needs_review"] or conflict
		return res
	if c["clear"] and c["value"] <= base_hi:
		res["outcome"]["closing"] = "not_above_opening"  # R4 / M4
		res["lines"]["closing"] = _line("closing", c, "the closing reading is not above the opening")
		res["needs_review"] = True
		return res
	pair_ok = bool(
		not blocked
		and o
		and o["clear"]
		and o["value"] == 0
		and c["clear"]
		and c["value"] > 0
		and o.get("drum_count") in (None, c["drum_count"])
		and o.get("decimal_present") in (None, c["decimal_present"])
	)
	if pair_ok:
		session = c["value"] - o["value"]
		why = cross_checks(session, session, True)
		if abs(litres - session) <= EXACT and not why:
			res["write"] = {"closing_reading": c["value"]}  # R3: a completed draft (no warning, no submit)
			res["outcome"]["closing"] = "clear_written"
			return res
		res["outcome"]["closing"] = "clear_not_written"
		if (
			why
		):  # B-2 / C-1 / C-2: a clear reading that contradicts other evidence is not written and is escalated
			res["lines"]["closing"] = _line("closing", c, "not written: " + "; ".join(why))
			res["needs_review"] = True
			return res
		res["lines"]["closing"] = _line(
			"closing", c, f"entered litres {_fmt(litres)} differ from the reading"
		)
		res["needs_review"] = res["needs_review"] or abs(litres - session) > TOLERANCE
		return res
	# R5: any ambiguity, defect flag, missing or mismatched opening: no Float written
	res["outcome"]["closing"] = "ambiguous"
	lo, hi = c["low"] - base_hi, c["high"] - base_lo
	bits = (
		["drum counts differ between the photos"]
		if o and o.get("drum_count") not in (None, c["drum_count"])
		else []
	)
	why = cross_checks(lo, hi, False)
	if litres and not (lo - TOLERANCE <= litres <= hi + TOLERANCE):
		why.insert(0, f"entered litres {_fmt(litres)} outside the interval")
	material = bool(why)
	# the line names what escalates it (F-2), next to the informational drum-count note
	res["lines"]["closing"] = _line("closing", c, "; ".join(bits + why) or None)
	# M1 (lead ruling): a drum-count difference is recorded and blocks the write, but is not material by itself
	res["needs_review"] = res["needs_review"] or material
	return res


# ------------------------------------------------------------------ marker Comments, attempts, crops
def marker_prefix(side, sha):
	return f"{MARKER_PREFIX} [{side}] {sha[:16]} v"


_SIGNED = re.compile(r": ([a-z_]{3,24}) #([0-9a-f]{16})$")


def _sign(fill, side, sha, outcome):
	"""F2: a marker is trusted only with this signature (site secret), so a Comment typed by a user cannot fabricate a
	'clear zero opening' or suppress an extraction."""
	from frappe.utils.password import get_encryption_key

	msg = f"{fill}|{side}|{sha[:16]}|{outcome}".encode()
	return hmac.new(cstr(get_encryption_key()).encode(), msg, hashlib.sha256).hexdigest()[:16]


def find_marker(fill, side, sha):
	"""The outcome token of an earlier pass over the same photo bytes whose signature verifies, or None."""
	rows = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Project Diesel Fill",
			"reference_name": fill,
			"comment_type": "Info",
			"content": ["like", marker_prefix(side, sha) + "%"],
		},
		pluck="content",
		limit=20,
	)
	for content in rows:
		m = _SIGNED.search(cstr(content).strip())
		if m and hmac.compare_digest(m.group(2), _sign(fill, side, sha, m.group(1))):
			return m.group(1)
	return None


def add_marker(doc, side, sha, engine, outcome):
	"""One signed audit Comment per photo pass: engine version and the first 12 hex of the models hash (L2)."""
	doc.add_comment(
		"Info",
		f"{marker_prefix(side, sha)}{engine['version']} m={engine.get('models', 'none')}: {outcome} "
		f"#{_sign(doc.name, side, sha, outcome)}",
	)


def _cache():
	return frappe.cache() if callable(frappe.cache) else frappe.cache


def _attempt_key(fill, side, sha):
	return f"card_meter_attempts:{fill}:{side}:{sha[:16]}"


def attempts_so_far(fill, side, sha):
	try:
		return int(_cache().get_value(_attempt_key(fill, side, sha)) or 0)
	except (TypeError, ValueError):
		return 0


def note_failure(fill, side, sha):
	"""Per fill+photo cap: three failures within 24 h are counted in the cache; the third writes the only marker."""
	n = attempts_so_far(fill, side, sha) + 1
	_cache().set_value(_attempt_key(fill, side, sha), n, expires_in_sec=24 * 3600)
	return n


def make_crop(image, box, size):
	"""JPEG bytes of the counter box (+4%), clamped to the image. None only for an invalid box (no size, or nothing left after
	clamping), a box whose area is over 60% of the image area, or one taller than 60% of the image: that is not a counter crop.
	The width alone never refuses: a close-up meter is a wide box. A box up to these limits is accepted as is; the crop comes from
	the same private photo of the same fill, so it shows nothing the photo does not."""
	from PIL import Image

	x, y, w, h = box
	if w <= 0 or h <= 0 or w * h > 0.6 * size[0] * size[1] or h > 0.6 * size[1]:
		return None
	mx, my = w * CROP_MARGIN, h * CROP_MARGIN
	area = (
		max(0, int(x - mx)),
		max(0, int(y - my)),
		min(size[0], int(x + w + mx)),
		min(size[1], int(y + h + my)),
	)
	if area[2] <= area[0] or area[3] <= area[1]:
		return None
	with Image.open(io.BytesIO(image)) as im:
		out = io.BytesIO()
		im.convert("RGB").crop(area).save(out, "JPEG", quality=92)
	return out.getvalue()


def attach_crop(doc, side, reading, image):
	"""A private File attached to the fill (the counter only, never the overlay); idempotent by file name."""
	if reading.get("status") != "ok" or "box" not in reading:
		return None
	data = make_crop(image, reading["box"], reading["image_size"])
	name = f"meter-crop-{side}-{reading['sha'][:16]}-v{reading['engine']['version']}.jpg"
	if not data or frappe.db.exists(
		"File", {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "file_name": name}
	):
		return None
	f = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": name,
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"is_private": 1,
			"content": data,
		}
	)
	f.insert()
	return f.name


# ------------------------------------------------------------------ hooks and the job
def after_fill_saved(doc, method=None):
	"""doc_events on_update of Project Diesel Fill: (1) markers + crops for an extraction just applied by validate,
	(2) enqueue a new extraction when a meter photo is new or changed. No-ops with the worker off."""
	applied = doc.flags.pop("meter_extraction_outcome", None)
	if applied:
		images = doc.flags.pop("meter_extraction_images", {})
		for side, token in applied["outcome"].items():
			r = applied["readings"].get(side)
			if not r or r["engine"]["name"] == "earlier":
				continue  # no reading this pass, or a remembered one (its marker already exists)
			add_marker(doc, side, r["sha"], r["engine"], token)
			if side in images:
				try:
					attach_crop(doc, side, r, images[side])
				except Exception:
					frappe.log_error(f"meter crop failed for {doc.name}", "CARD meter extraction")
	if not worker_config() or doc.docstatus != 0 or doc.flags.get("in_meter_extraction"):
		return
	if any(doc.get(f) and doc.has_value_changed(f) for f in PHOTO_FIELD.values()):
		frappe.enqueue(
			"card.diesel_meter_extraction.run_extraction",
			queue="long",
			timeout=120,
			enqueue_after_commit=True,
			fill=doc.name,
		)


def _photo_bytes(doc, field):
	"""(bytes, content type) of the private photo behind the field, checked like every CARD attachment."""
	from card.attachment_validator import IMAGE_KINDS, check_content

	url = cstr(doc.get(field))
	rows = frappe.get_all(
		"File",
		filters={"file_url": url, "is_folder": 0, "is_private": 1},
		fields=["name", "file_name"],
		limit=1,
	)
	if not rows or not url.startswith("/private/files/"):
		raise WorkerError("no_file")
	# the RAW bytes from disk: File.get_content() may return a decoded str, which corrupts a photo (same rule as
	# attachment_validator); the path comes from a url matched to a private File row and stays inside private/files
	base = os.path.realpath(frappe.get_site_path("private", "files"))
	path = os.path.realpath(frappe.get_site_path(*url.lstrip("/").split("/")))
	if os.path.commonpath([base, path]) != base:
		raise WorkerError("outside_private_files")
	with open(path, "rb") as handle:
		content = handle.read(MAX_PHOTO_BYTES + 1)
	return content, "image/" + check_content(content, rows[0].file_name, IMAGE_KINDS)


def _prior_stub(side, token, sha):
	"""An earlier clear-zero opening is remembered by its marker, so a later closing photo can complete the pair."""
	if side == "opening" and token == "clear_zero":
		return {
			"status": "ok",
			"clear": True,
			"value": 0.0,
			"low": 0.0,
			"high": 0.0,
			"flags": [],
			"text": "0",
			"drum_count": None,
			"decimal_present": None,
			"sha": sha,
			"side": side,
			"engine": {"name": "earlier", "version": "pass"},
		}
	return None


def run_extraction(fill):
	"""The background job. frappe.enqueue carries the saving user; a job without a user (a retried job) does nothing.
	I/O and validation only: the decision is taken by the fill's own validate()."""
	if frappe.session.user in (None, "", "Guest"):
		return "no_user"
	config = worker_config()
	if not config:
		return "worker_off"
	if not frappe.db.exists("Project Diesel Fill", fill):
		return "missing"
	from frappe.utils.synchronization import LockTimeoutError, filelock

	try:
		# M2 / F6: one job per fill at a time; a duplicate job waits, then finds the markers of the first one
		with filelock(f"card_meter_extraction_{fill}", timeout=120):
			return _extract_locked(fill, config)
	except LockTimeoutError:
		return "busy"


def _extract_locked(fill, config):
	"""Returns a short status string (also what the tests assert on): applied, not_editable, no_permission, nothing_new."""
	doc = frappe.get_doc("Project Diesel Fill", fill)
	if doc.docstatus != 0 or doc.review_status not in EDITABLE:
		return "not_editable"
	if not doc.has_permission("write"):
		return "no_permission"
	readings, images, fresh = {}, {}, False
	for side, field in PHOTO_FIELD.items():
		if not doc.get(field):
			continue
		try:
			image, ctype = _photo_bytes(doc, field)
		except Exception as exc:
			frappe.logger("card.meter_extraction").warning(
				f"{fill} {side} photo unreadable: {type(exc).__name__}"
			)
			continue
		sha = hashlib.sha256(image).hexdigest()
		token = find_marker(fill, side, sha)
		if token:
			stub = _prior_stub(side, token, sha)
			if stub:
				readings[side] = stub
			continue
		if attempts_so_far(fill, side, sha) >= MAX_ATTEMPTS:
			continue
		try:
			reading = call_worker(config, side, sha, image, ctype)
		except WorkerError as exc:
			frappe.logger("card.meter_extraction").warning(f"{fill} {side} {sha[:8]} {exc}")
			# M2 / F5: a busy, unavailable or unreachable worker is retry-later: only invalid answers count toward the cap
			if not exc.transient and note_failure(fill, side, sha) >= MAX_ATTEMPTS:
				add_marker(doc, side, sha, {"version": "0", "models": "none"}, "worker_error")
			continue
		readings[side], images[side], fresh = reading, image, True
	if not fresh:
		return "nothing_new"  # worker off, failed, or every photo already processed
	doc.flags.meter_extraction = readings
	doc.flags.meter_extraction_images = images
	doc.flags.in_meter_extraction = True
	doc.save()
	return "applied"


# ------------------------------------------------------------------ helper for the fill's validate()
def split_block(text):
	"""{side: extraction line} found in a saved evidence_warnings value."""
	block = {}
	for line in cstr(text).splitlines():
		for side in SIDES:
			if line.startswith(LINE_PREFIX.format(side)):
				block[side] = line
	return block
