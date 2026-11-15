#!/usr/bin/env python3
"""Image gate for the captured documentation screenshots (run after capture, before the artifact upload).

Rules:
- A group of shots with identical image bytes is allowed only when every shot in it except one canonical shot
  declares "allowDuplicateOf": "<canonical name>" in shots.json. An undeclared duplicate is a defect (a screen that
  was not what its name says, repeated).
- The required volume-billing set must exist, non-empty, in EN and AR.
- Each duplicate is reported with its shot names and the route the capture logged for it.

Usage: check_images.py <screenshots root> <capture log> <shots.json>
Exit status 1 when any rule fails. Stdlib only, so it runs without the website dependencies.
"""

import hashlib
import json
import os
import re
import sys
from collections import defaultdict

LANGS = ("en", "ar")
REQUIRED = [
	"volume-billing-equipment-commercial",
	"volume-billing-monthly-card-days",
	"volume-billing-card-totals",
	"volume-billing-print",
	"volume-billing-customer-statement",
	"volume-billing-loads-card",
]


def route_for(log, lang, name):
	matches = re.findall(r"\[route\] " + re.escape(f"{lang}/{name}") + r" -> (\S+)", log)
	return matches[-1] if matches else "no route logged"


def check(root, log_path, shots_path):
	with open(shots_path, encoding="utf-8") as fh:
		shots = {s["name"]: s for s in json.load(fh)["shots"]}
	log = ""
	if os.path.exists(log_path):
		with open(log_path, encoding="utf-8", errors="replace") as fh:
			log = fh.read()
	failures = []
	for lang in LANGS:
		folder = os.path.join(root, lang)
		files = sorted(f for f in os.listdir(folder) if f.endswith(".webp")) if os.path.isdir(folder) else []
		groups = defaultdict(list)
		for f in files:
			with open(os.path.join(folder, f), "rb") as fh:
				groups[hashlib.sha256(fh.read()).hexdigest()].append(f[: -len(".webp")])
		for names in groups.values():
			if len(names) < 2:
				continue
			names = sorted(names)
			canon = [n for n in names if not shots.get(n, {}).get("allowDuplicateOf")]
			declared = len(canon) == 1 and all(
				shots.get(n, {}).get("allowDuplicateOf") == canon[0] for n in names if n != canon[0]
			)
			if not declared:
				described = "; ".join(f"{n} [{route_for(log, lang, n)}]" for n in names)
				failures.append(f"duplicate images in {lang} not declared in shots.json: {described}")
		for name in REQUIRED:
			path = os.path.join(folder, name + ".webp")
			if not (os.path.isfile(path) and os.path.getsize(path) > 0):
				failures.append(f"missing {lang}/{name}")
	return failures


def main(argv):
	if len(argv) != 4:
		print(__doc__)
		return 2
	failures = check(argv[1], argv[2], argv[3])
	for line in failures:
		print(f"::error::{line}")
	if failures:
		return 1
	print("IMAGE GATE OK")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
