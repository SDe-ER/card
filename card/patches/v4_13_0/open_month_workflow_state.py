"""FR-191: the Workflow State "Open – month not ended" and its two transitions on the CARD monthly card Workflow
(added when missing; nothing existing is changed; the Workflow stays inactive when it is inactive). No card is
changed by this patch: reopening a card is a separate, explicit action (``card.open_month``)."""

from card.open_month import ensure_open_month_state


def execute():
	ensure_open_month_state()
