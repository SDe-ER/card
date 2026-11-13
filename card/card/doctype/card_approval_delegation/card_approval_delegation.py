# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-163 (WP-D5; #35 G4 delegation; closure plan C-12, owner decision O-12): Card Approval Delegation.

A delegation lets ``delegate_user`` act on ``delegator_user``'s approval queue for a CARD DocType
(Card Monthly Card, Equipment Transport, Project Diesel Fill) within a date window, scoped by company
and ``approval_scope``.

Owner decision O-12 (approved 2026-11-10): delegation WITHOUT role grants. The delegate must already
hold the SAME CARD approver role as the delegator; the DocType validates both sides on insert. The
guard in ``card.governance`` lets the delegate inherit the delegator's authority (SoD creator-check,
tier-role-check, workflow-state-edit roles) within the scope; the delegate IS the acting user, they
just inherit. No DocPerm is widened by a delegation row.

Server rules (every save route — form save, REST insert and PUT, ``frappe.client.save/set_value``,
savedocs, bulk update):

- ``delegator_user``, ``delegate_user``, ``company``, ``from_date``, ``to_date``, ``reason`` and
  ``approval_scope`` are mandatory (DocType JSON ``reqd``).
- ``delegator_user`` must hold at least one CARD approver role: Card Manager, Card Reviewer or
  Accounts Manager (``CARD_APPROVER_ROLES``).
- ``delegate_user`` must hold EVERY CARD approver role the delegator holds (the delegate's role set
  is a superset of the delegator's CARD approver role set). This proves the delegate is independently
  capable of approving on the delegator's queue; the delegation grants no role.
- ``from_date`` <= ``to_date``.
- No overlapping active delegation for the same (delegator, approval_scope, company) across the date
  range; the scope "All CARD approvals" overlaps with every other scope. The check uses
  ``frappe.qb ... .for_update()`` on the stored rows so two concurrent inserts cannot both succeed
  (Lesson 4).
- ``status`` is server-written: Active in the window, Expired after ``to_date``, Cancelled on
  ``docstatus = 2``. A client value sent for ``status`` is always dropped (Lesson 1).

Routes covered: validate, before_save, before_submit, before_update_after_submit, before_cancel. The
cancel path reuses the FR-123 ``_refuse_changes`` pattern in ``on_cancel`` (Lesson 2).

Idempotency: a second insert with the same (delegator, scope, company, window) is refused by the
overlap check, not by a UNIQUE index (the overlap goes further: it covers every intersection).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from card.cancel_reason import _refuse_changes

CARD_APPROVER_ROLES = ("Card Manager", "Card Reviewer", "Accounts Manager")

SCOPE_ALL = "All CARD approvals"
SCOPE_MONTHLY_CARD = "Monthly Cards"
SCOPE_TRANSPORT = "Transports"
SCOPE_DIESEL = "Diesel Fills"

SCOPE_TO_DOCTYPE = {
	SCOPE_MONTHLY_CARD: "Card Monthly Card",
	SCOPE_TRANSPORT: "Equipment Transport",
	SCOPE_DIESEL: "Project Diesel Fill",
}

DOCTYPE_TO_SCOPE = {v: k for k, v in SCOPE_TO_DOCTYPE.items()}

STATUS_ACTIVE = "Active"
STATUS_EXPIRED = "Expired"
STATUS_CANCELLED = "Cancelled"


class CardApprovalDelegation(Document):
	"""Server-side controller."""

	def validate(self):
		# Server-written status: any client value is dropped on every save (Lesson 1).
		self.status = self._resolve_status()
		self._validate_window()
		self._validate_delegator_role()
		self._validate_delegate_role()
		self._validate_no_overlap()

	def before_submit(self):
		# Submit path re-runs the overlap check under a locking read (Lesson 4):
		# a second parallel submit of an overlapping delegation is refused here.
		self._validate_no_overlap(for_update=True)
		self.status = self._resolve_status()

	def before_update_after_submit(self):
		# A submitted delegation is immutable on routine update paths: restore the
		# server-written status from the stored row (Lesson 1 server-written restore).
		stored = _stored_delegation(self.name)
		if stored:
			self.status = stored.get("status") or self._resolve_status()

	def before_cancel(self):
		# A cancel request may carry forged values on every route (Lesson 2: Frappe skips
		# validate on cancel). ``_refuse_changes`` compares meta fields + owner/creation +
		# child idx/owner/creation against the stored row and refuses any change. ``neutral``
		# wording because this DocType has no "approved" semantics.
		_refuse_changes(self, self.get_latest(), neutral=True)
		# Server-written after the comparison: Frappe's db_update on cancel writes every column.
		self.status = STATUS_CANCELLED

	def on_cancel(self):
		# Every use of (or action on) a delegation is logged.
		self.add_comment(
			"Info",
			_("Delegation cancelled by {0}.").format(frappe.session.user),
		)

	# ------------------------------------------------------------------
	# Validation helpers
	# ------------------------------------------------------------------
	def _validate_window(self) -> None:
		if not self.from_date or not self.to_date:
			return
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(
				_("Delegation ``from_date`` must not be after ``to_date``."),
				title=_("Delegation window"),
			)

	def _validate_delegator_role(self) -> None:
		roles = _card_approver_roles_of(self.delegator_user)
		if not roles:
			frappe.throw(
				_(
					"Delegator {0} does not hold any CARD approver role ({1}); a delegation can only be granted by an approver."
				).format(self.delegator_user, ", ".join(CARD_APPROVER_ROLES)),
				title=_("Delegation delegator role"),
			)

	def _validate_delegate_role(self) -> None:
		"""Owner O-12: the delegate must already hold EVERY CARD approver role the delegator
		holds; delegation grants no role. A single missing role refuses the save."""
		if self.delegator_user == self.delegate_user:
			frappe.throw(
				_("Delegator and delegate must be different users."),
				title=_("Delegation users"),
			)
		delegator_roles = _card_approver_roles_of(self.delegator_user)
		delegate_roles = _card_approver_roles_of(self.delegate_user)
		missing = delegator_roles - delegate_roles
		if missing:
			frappe.throw(
				_(
					"Delegate {0} must already hold the delegator's CARD approver roles; missing: {1}. Delegation grants no role."
				).format(self.delegate_user, ", ".join(sorted(missing))),
				title=_("Delegation delegate role"),
			)

	def _validate_no_overlap(self, for_update: bool = False) -> None:
		"""Refuse an active delegation that overlaps another one for the same (delegator,
		approval_scope, company) across the date range. The scope ``SCOPE_ALL`` overlaps
		with every other scope for the same delegator and company.

		Lesson 4: ``for_update=True`` locks the stored rows so two concurrent submits of
		overlapping delegations cannot both pass the check."""
		if not (self.delegator_user and self.company and self.from_date and self.to_date):
			return
		table = frappe.qb.DocType("Card Approval Delegation")
		query = (
			frappe.qb.from_(table)
			.select(table.name, table.approval_scope, table.from_date, table.to_date)
			.where(table.delegator_user == self.delegator_user)
			.where(table.company == self.company)
			.where(table.docstatus != 2)
			.where(table.status != STATUS_CANCELLED)
			.where(table.from_date <= getdate(self.to_date))
			.where(table.to_date >= getdate(self.from_date))
		)
		if self.name:
			query = query.where(table.name != self.name)
		if for_update:
			query = query.for_update()
		for row in query.run(as_dict=True):
			if self._scopes_overlap(row.approval_scope):
				frappe.throw(
					_(
						"Delegator {0} already has an active delegation {1} for {2} / {3} between {4} and {5}."
					).format(
						self.delegator_user,
						row.name,
						self.company,
						row.approval_scope,
						row.from_date,
						row.to_date,
					),
					title=_("Delegation overlap"),
				)

	def _scopes_overlap(self, other_scope: str) -> bool:
		if self.approval_scope == SCOPE_ALL or other_scope == SCOPE_ALL:
			return True
		return self.approval_scope == other_scope

	def _resolve_status(self) -> str:
		if self.docstatus == 2:
			return STATUS_CANCELLED
		if not self.to_date:
			return STATUS_ACTIVE
		if getdate(self.to_date) < getdate(today()):
			return STATUS_EXPIRED
		return STATUS_ACTIVE


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------
def _card_approver_roles_of(user: str | None) -> set[str]:
	if not user:
		return set()
	return {r for r in frappe.get_roles(user) if r in CARD_APPROVER_ROLES}


def _stored_delegation(name: str) -> dict | None:
	if not name:
		return None
	return frappe.db.get_value(
		"Card Approval Delegation", name, ["status", "docstatus"], as_dict=True, for_update=True
	)


def expire_delegations_past_to_date() -> int:
	"""Scheduled daily job. Sets ``status = "Expired"`` for every submitted delegation whose
	``to_date`` is strictly before today. Idempotent and safe on a second run. A rolled-back
	code change leaves the status column as data — no DocType rollback impact.

	Returns the number of rows updated (useful for tests)."""
	if not frappe.db.exists("DocType", "Card Approval Delegation"):
		return 0
	table = frappe.qb.DocType("Card Approval Delegation")
	rows = (
		frappe.qb.from_(table)
		.select(table.name)
		.where(table.docstatus == 1)
		.where(table.status == STATUS_ACTIVE)
		.where(table.to_date < getdate(today()))
		.run(as_dict=True)
	)
	for row in rows:
		frappe.db.set_value(
			"Card Approval Delegation",
			row.name,
			"status",
			STATUS_EXPIRED,
			update_modified=False,
		)
	return len(rows)
