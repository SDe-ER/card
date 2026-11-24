# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Issue 50 (owner decision 2026-11-24): the code no longer falls back to 260 standard month hours or a 12-hour
shift limit when Card Settings has no value. So that an upgraded site behaves exactly as before, this patch
stores the DocType default of each hour setting that has no stored value. A stored value, also an explicit 0,
is never replaced. Idempotent.

Writes: at most three Card Settings values. No document, amount or permission."""

from card.settings import store_hour_settings_defaults


def execute():
	store_hour_settings_defaults()