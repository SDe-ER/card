# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Issue 50 (owner decision 2026-11-24): the code no longer falls back to 260 standard month hours or a 12-hour
shift limit when Card Settings has no value. So that an upgraded site behaves exactly as before, this patch
stores the DocType default of each hour setting that has no stored value or a stored 0 (the old code read both
as "use the built-in number"). A value above 0 is never replaced. It runs once; from then on a 0 means "not
configured".

Writes: at most three Card Settings values. No document, amount or permission."""

from card.settings import store_hour_settings_defaults


def execute():
	store_hour_settings_defaults(replace_zero=True)
