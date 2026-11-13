---
title: What's new
description: Every change to CARD in plain language — what is merged and waiting for the next release, and what each released version brought.
sidebar:
  order: 1
---

This page lists every change to CARD in plain language, newest first. Each entry says what changed and what it
means for the people who use CARD. The full technical record is the
[CHANGELOG](https://github.com/SDe-ER/card/blob/main/CHANGELOG.md) and the
[release notes](https://github.com/SDe-ER/card/tree/main/docs/releases) in the repository.

:::note[Merged is not released, released is not deployed]
A change listed under **Next release** is in the code on `main` but not yet in a published version. A published
version is not running on a site until that site is upgraded. Which version a site runs is decided and checked
per site.
:::

## Next release (merged, not yet released)

### Documentation

- **2026-11-12 — "What's new" in two languages and a shorter README.** This page now records every change in
  English and Arabic. The repository README is a short entry point that links here for the details.
- **2026-11-11 — Screenshots, generated Reference and a new Arabic font.** Every documented screen now has a
  screenshot in English and in Arabic, taken from a demo site with invented data. A new
  [Reference](/card/reference/) section is built from the code on every build: every DocType with its fields
  and permissions, every report with its filters, and every API method. Arabic text uses IBM Plex Sans Arabic.
  The site is rebuilt automatically whenever the CARD code changes.
- **2026-11-10 — This documentation site.** Getting started, features, reports and the API reference, in
  English and Arabic.

### Operations

- **2026-11-13 — Approval delegation that grants no role.** The owner can now create a Card Approval Delegation
  that lets one approver act on another approver's queue for a date window and a chosen scope (all CARD approvals
  or only monthly cards, transports or diesel fills), for a given company. The delegation does **not** grant any
  role to the delegate: the delegate must already hold the same CARD approver role as the delegator (Card Manager,
  Card Reviewer or Accounts Manager), and the save is refused otherwise. Inside the window, the delegate's submit
  of a monthly card inherits the delegator's identity for the separation-of-duties and approval-tier checks only;
  every such use is logged on the card. A delegation expires automatically after its end date (daily job), and a
  cancellation is audited. Empty catalog = today's behaviour unchanged; no new role, permission or API endpoint.
- **2026-11-13 — Approval tiers for the monthly card.** Each company can now add approval-tier thresholds to its
  row in Card Settings (Monthly card approval tiers): a tier names a net-amount threshold and the role a user
  must already hold to submit a card at or above that amount. A company with no thresholds behaves exactly as
  today — any user who may write a monthly card may submit it. With thresholds, the card's resolved tier is
  shown on the form (read-only, server-written), and the office picks the role for each tier from the roles
  the owner already has — no new role or permission is added. The highest matching threshold wins; a refund
  (negative amount) is gated by its absolute size. A matching ERPNext Authorization Rule on the generated
  Purchase or Sales Invoice complements the source gate at the invoice side; the owner configures the two
  together per company. Administrator is not exempt from the tier gate.
- **2026-11-13 — Party portal scaffold, built but not reachable yet.** The groundwork for the supplier /
  customer portal that will let a partner see only their own monthly cards is now in the code. In this release
  it is **not reachable**: every URL under `/card-portal` returns "page not found", no permission is granted to
  the Supplier or Customer roles, and the preview switch on Company settings is off on every company. A later
  release wires the routes and the permission hook, and the owner turns the switch on per company when he is
  ready. The owner's 2026-11-10 decision is kept: the portal is in scope, off by default.
- **2026-11-13 — Equipment operating groups and a Diesel Group Analysis report.** An operating group is a named
  set of machines that work together — for example a crusher plant made of a crusher, a generator and an
  excavator. Each group belongs to one company; a machine belongs to at most one active group of its company at
  a time; when the machine should move to another group, its dates are set and a new group opens on the next
  day. The new **Diesel Group Analysis** report shows, for one company and a date range, the litres the group's
  machines received: direct fills marked **measured**, and tank-fill shares marked **estimated** (never
  re-labelled measured). A separate "shared bucket (outside the group)" line shows what the same tank fill
  delivered to machines that are not in the group, so the two numbers never overlap and the fill's litres add up
  exactly once. Groups do not change any card, any fill or any accounting — they are a reading tool only. An
  empty catalog of groups keeps everything as it is today.
- **2026-11-13 — Where a day on a monthly card came from.** Each day row on a monthly card can now record its
  source (manual — the default, paper sheet, WhatsApp, mobile app or import), an optional external key (sheet
  number, message id) and the time the office received the source. A day's intake fields are optional, and a card
  entered by hand carries "manual" as before. When the source and the key are both filled in, the same pair cannot
  be used on two days in the same company and month — one sheet or one message names one day. A fingerprint
  (SHA-256) of the source document is stored next to the day; it is written by the server and never by the user.
  After a card is submitted its source fields never change.
- **2026-11-12 — Allocation rows for tank diesel fills (display only).** When a project-tank diesel fill is
  submitted, CARD now stores a per-machine estimated split of the litres, frozen at submit, so reports and the
  card always read the same figures. Each company chooses the weighting — share by hours (the default, same as
  before) or share by hours × litres-per-hour. The posting still books the fill as one project-level line; the
  rows never reach the general ledger. A machine with no hours or no rate is kept in the list with a review
  flag and no litres, and the rounding remainder is marked on one row so the row litres always add up to the
  fill litres.
- **2026-11-12 — Daily logs on CARD Mobile.** Operators can now record their daily logs from their phones: list
  their own logs, create and edit a draft (day, night and stopped hours per machine), send it to the supervisor, and
  correct a log that was returned with a reason. See [CARD Mobile](/card/features/card-mobile/) and
  [Daily logs](/card/features/daily-logs/).
- **Daily logs.** Site supervisors record each machine's day and night hours per project and day. A manager
  approves the log, and draft monthly cards can be generated from approved logs. See
  [Daily logs](/card/features/daily-logs/).
- **Meter readings.** Weekly engine-hour readings per machine, kept as their own records. See
  [Meter readings](/card/features/meter-readings/).
- **Day billing basis per machine.** Each machine is billed either *prorated by hours* (the default) or as a
  *full day* when it worked at all that day. See [Equipment](/card/features/equipment/).
- **Downtime rules.** Every stop records who is responsible and whether the stopped hours are billable.
- **Diesel consumption rates by date.** A default rate per equipment type with an override per machine, each
  valid from a date.
- **Diesel price on each fill.** Each fill keeps the currency, unit and valid-from date of the price used.
- **Where a transport request came from.** A transport can record how it was received (manual entry, paper or
  WhatsApp) with its evidence.
- **Main store and tool-custody store per company**, and a time window for repeated material requests.

### Accounting and control

- **2026-11-12 — Approved period run before posting (optional per company).** A company can require that a
  month's cards, diesel fills and transports are in an approved, up-to-date Card Period Run before they are posted.
  Off by default. See [Invoicing and posting](/card/features/invoicing-posting/#period-run-before-posting-opt-in).
- **Separation of duties on monthly cards.** The people who prepared a card are recorded. Each company chooses
  whether a preparer who submits the card only gets a warning (the default) or is refused. See
  [Monthly cards](/card/features/monthly-cards/).
- **Card Period Run.** A versioned monthly run of a period's cards with accountant approval.
- **Transport cost posting per company:** *Hold* (the default) keeps transport costs out of posting until
  reviewed; *Post* includes them.
- **Dated rate agreements** can be recorded. They are not used in pricing yet.
- **Posting Source Integrity report** finds sources whose invoice link and "posted" flag disagree.
- **Reports show money in the company currency.**
- **Card Reviewer role** for the review step that is planned.

### Security

- **2026-11-12 — Native-workflow state guards.** When an owner activates a CARD approval workflow (optional,
  off by default), the server now refuses a save from any route by a user who does not hold an edit role for
  the stored state — the form lock applied from Desk earlier is now applied to REST, bulk updates and
  `frappe.client` calls too. Behaviour is unchanged while every CARD workflow stays inactive.
- A cancelled daily log or meter reading can no longer be rewritten.
- The evidence attached to a submitted transport is kept.
- Users limited to some companies see only those companies in Card Settings.
- Rows inside a document follow the access level of their table.

## Released versions

| Version | Date | What it brought |
|---|---|---|
| [4.7.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.7.0.md) | 2026-11-10 | Company checks on tool custody and on equipment needs requests and reviews; VAT rate taken from the company's tax templates; equipment status check on diesel fills; Equipment Location History report; role and action matrix |
| [4.6.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.6.0.md) | 2026-11-10 | Security fixes (read-only requests, attachment checks, a reviewer cannot also approve); a reason is required to cancel; stop reasons and the Equipment Downtime report; diesel prices by date; per-company checks on equipment and diesel; posting preview page; three analysis reports |
| [4.5.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.5.0.md) | 2026-11-09 | A supplier accrual journal entry can be linked to its cards so they are never invoiced again; Card Settlement Status report (paid and remaining per card) |
| [4.4.3](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.4.3.md) | 2026-11-09 | The supplier statement PDF prints on one A4 portrait page with correctly joined Arabic letters |
| [4.4.2](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.4.2.md) | 2026-11-09 | The A4 supplier statement prints every card of the period and totals from the cards only |
| [4.4.1](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.4.1.md) | 2026-11-09 | Arabic letters join correctly in PDF prints; shorter totals on the supplier statement |
| [4.4.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.4.0.md) | 2026-11-09 | One print style for every CARD print; prints follow the print language and direction |
| [4.3.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.3.0.md) | 2026-11-09 | Posting checks and project cost centers; transport cost responsibility; review reports; equipment money privacy; night-shift customer rate |
| [4.2.2](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.2.2.md) | 2026-10-27 | Larger diesel meter photos and clearer reading labels |
| [4.2.1](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.2.1.md) | 2026-10-27 | Simpler diesel fill form |
| [4.2.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.2.0.md) | 2026-10-27 | Diesel fill as a metered session with meter photos and a review; diesel session import; parts fitment; the app is named CARD |
| [4.1.2](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.1.2.md) | 2026-10-25 | Full launcher navigation on upgraded sites; simpler transport form; English names for stored Arabic values |
| [4.1.1](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.1.1.md) | 2026-10-25 | Item search fix in tool custody |
| [4.1.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.1.0.md) | 2026-10-25 | First production candidate: unique chassis and plate numbers, rehearsed upgrade, isolation fixes |
| [4.0.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.0.0.md) | 2026-10-19 | Equipment materials: operator requests, supervisor review, approval into draft Material Requests, tool custody |
| [3.0.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v3.0.0.md) | 2026-10-19 | CARD launcher, multi-machine transport, cards follow transports, equipment from ERPNext Assets |
| [1.2.2](https://github.com/SDe-ER/card/blob/main/docs/releases/v1.2.2.md) | 2026-10-18 | Company isolation, protected equipment fields, permanent posting log |
| [1.2.1](https://github.com/SDe-ER/card/blob/main/docs/releases/v1.2.1.md) | 2026-10-16 | Report filters for operational roles; amounts on prints |
| [1.2.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v1.2.0.md) | 2026-10-16 | Rental directions and customers, settings and roles, diesel and transport, accounting dimension |
| [1.0.1](https://github.com/SDe-ER/card/blob/main/docs/releases/v1.0.1.md) | 2026-10-13 | Compatibility fixes for Frappe 16.50 and 16.51 |
| [1.0.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v1.0.0.md) | 2026-10-13 | First release |

CARD follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). See also the
[version history](https://github.com/SDe-ER/card/blob/main/docs/releases/VERSION-HISTORY.md),
[which version to use](https://github.com/SDe-ER/card/blob/main/docs/releases/WHICH-VERSION.md) and the
[release policy](https://github.com/SDe-ER/card/blob/main/docs/releases/RELEASE-POLICY.md).
