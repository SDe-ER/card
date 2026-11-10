# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v4.8.0 (FR-137, #35 Q2): create the Card Reviewer role on existing sites.

Uses the same idempotent ensure_card_roles() as before_install, so a fresh install and an
upgraded site end up identical. Existing roles are left as they are. No user is given the
role and no DocPerm is added: later governance packages wire it and the owner assigns it."""

from card.install import ensure_card_roles


def execute():
	ensure_card_roles()
