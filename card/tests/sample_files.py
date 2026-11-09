# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Synthetic attachment bytes for tests: real, tiny, decodable files (the attachment validator
checks the content, so a text stand-in is no longer accepted)."""

import hashlib
import io


def png(seed: str = "") -> bytes:
	"""A valid 8x8 PNG whose colour (so its bytes) follows `seed`."""
	from PIL import Image

	colour = tuple(hashlib.sha256(seed.encode()).digest()[:3])
	buffer = io.BytesIO()
	Image.new("RGB", (8, 8), colour).save(buffer, "PNG")
	return buffer.getvalue()


def pdf(seed: str = "") -> bytes:
	"""A minimal well-formed one-page PDF (real xref table, readable by PDF libraries); `seed` goes into
	its /Title so the bytes are unique."""
	title = "".join(c for c in seed if c.isalnum() or c == " ")
	objects = [
		b"<</Type/Catalog/Pages 2 0 R>>",
		b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
		b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 72 72]>>",
		f"<</Title({title})>>".encode(),
	]
	out = b"%PDF-1.4\n"
	offsets = []
	for number, body in enumerate(objects, start=1):
		offsets.append(len(out))
		out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
	xref = len(out)
	out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
	out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
	out += f"trailer\n<</Size {len(objects) + 1}/Root 1 0 R/Info 4 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
	return out
