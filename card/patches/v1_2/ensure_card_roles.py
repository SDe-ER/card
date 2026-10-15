# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Create the "Card Manager" / "Card User" roles on sites installed before
they existed. Idempotent."""


def execute():
	from card.install import ensure_card_roles

	ensure_card_roles()
