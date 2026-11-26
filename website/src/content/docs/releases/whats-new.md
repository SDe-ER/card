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

_Nothing yet._

## v4.13.0 — 2026-11-26

Minor release on top of v4.12.2. One rule changes: a Monthly Card is approved only after its month ends. It adds one equipment field and one report. It changes no role or permission, and CARD posts no accounting entry.

- **2026-11-25 — The equipment records who pays the maintenance.** **Equipment** has a new field, **Maintenance charged to**, next to **Operator charged to** on the **Cost and rental** tab. You select «المؤجر» (Lessor) or «الشركة» (Company), as for **Fuel charged to**. The field is empty until you set it. It is information only: it changes no card, invoice or accounting entry, and maintenance expenses are recorded by hand as before. It is a commercial term, so the users who can change the rate can change it, and a change of a value already set needs a reason; the first value needs none. No role or permission changes.
- **2026-11-25 — A new report shows the revenue and the expenses of each project.** **Project Invoice Profitability** is in **Card Reports**. Choose a company and a period, and optionally one project. For each project the report shows the revenue from the submitted sales invoices, the expenses from the submitted purchase invoices, the margin and the margin percentage, and a total row. The amounts are net of VAT, in the company currency. Credit notes and debit notes reduce their side. Expenses include every purchase invoice line, also stock and asset purchases. Opening invoices are not counted. Invoice lines without a project are on the row **No project**, so the totals equal the invoices. The report is read-only: it changes nothing and posts nothing. The margin is revenue minus purchase-invoice expenses. It is not the full net profit, because payroll, depreciation, overhead and costs booked by journal entry are not included. Only a System Manager or an Accounts Manager with General Ledger access to the company, who can read both sales invoices and purchase invoices, can run it. No role or permission changes.
- **2026-11-25 — A monthly card is approved only after its month ends.** You save a **Monthly Card** as often as you like during the month: add days, hours, additions and deductions, and save. Approval (Submit) is possible only from the first day of the next month (Riyadh time); before that the form shows the earliest approval date and the server refuses the approval on every route, also for Administrator. A card of an unfinished month that was already approved can be reopened by a System Manager with **Reopen for open month**: it keeps its number, its rows, attachments and comments, shows as **Provisional – month open, not approved**, and its days and additions/deductions can be changed and saved again. After the month ends, **Approve** freezes it. An open card is never posted to an invoice. No card is cancelled, amended or created by this.

## v4.12.2 — 2026-11-25

Patch release on top of v4.12.1. One fix. It changes no role, permission, accounting entry or stored value.

- **2026-11-25 — The PDF of the Equipment Customer Statement shows Arabic correctly.** The **PDF** action of the report **Equipment Customer Statement** drew the letter alef apart from the letter before it in some Arabic words. The PDF is now made on the server with the same generator as the **Equipment Supplier Statement**, so Arabic words are joined correctly. The layout, the figures and the **Print** action are the same as before. No role, permission or accounting rule changes.

## v4.12.1 — 2026-11-25

Patch release on top of v4.12.0. One fix. It changes no role, permission, accounting entry or stored value.

- **2026-11-25 — A company row in Card Settings opens for editing again.** In **Card Settings > Company settings**, the edit button of a row did not open the row, so a company's settings could not be changed in the form. The cause was the table **Approval tier thresholds** inside the row: the form cannot show a table inside a table row. The table is now in **Card Settings** itself, in the section **Monthly card approval tiers** below **Company settings**, and each of its rows names its company. Thresholds that are already stored stay as they are and show in the new place. A company cannot have two thresholds with the same amount or the same tier name: the save is refused. No role, permission or accounting rule changes.

## v4.12.0 — 2026-11-25

Minor release on top of v4.11.1. It adds three settings in **Card Settings > Company settings**. All three are off by default, so nothing changes until you turn one on. It changes no role, permission or accounting rule.

- **2026-11-25 — Loads can be entered on the daily log (off until you switch it on).** **Card Settings** has a new switch per company, **Loads on daily logs**, and it is off by default. While it is off, nothing changes: loads are entered on the **Monthly Card** as before. When it is on, a **Daily Log** row has **Day shift loads** and **Night shift loads** for a machine billed to its customer per m³, and **Generate monthly cards** copies them to the day and night cards. A daily log without loads does not erase loads typed on a card. Submitted cards are never changed. On a new daily log the two fields show after the first save. CARD Mobile has no load fields yet.
- **2026-11-25 — A second person can be required for transports entered from a paper sheet or a message.** **Card Settings > Company settings** has a new switch, **Transport from evidence needs a second person**, and it is off by default. While it is off, nothing changes. When a company turns it on, an **Equipment Transport** that names its source (a source key, a received time, an evidence file, or a channel such as Paper or WhatsApp) cannot be submitted by a user who created or edited it. Another user who may submit transports submits it. Transports without a source are not affected. No role or permission changes.
- **2026-11-25 — The suppliers summary can show partner-owned equipment apart.** **Card Settings → Company settings** has a new switch, **Show partner-owned equipment in the suppliers summary**, and it is off by default. While it is off, **Equipment Suppliers Summary** is unchanged. When you switch it on for a company, each supplier row also shows how many of its machines have the ownership **طرف ثالث** (a machine that belongs to a partner) and the net of the cards of those machines. The net is a card amount, so only users whose roles may read the amounts of a **Monthly Card** see it. The switch changes no permission and no accounting entry, and it does not calculate what a partner is owed after deductions.

## v4.11.1 — 2026-11-25

Patch release on top of v4.11.0. The Card Equipment accounting dimension is now created only when you switch it on in Card Settings, so the upgrade adds nothing to the accounting documents. It also brings the A4 print of the customer statement and several small fixes. It changes no role, permission or accounting rule.

- **2026-11-24 — Standard month hours and the shift limits come only from Card Settings.** CARD no longer uses a built-in 260 hours or 12 hours when these settings are empty or zero. If **Standard month hours** is not set, a per-month rate is refused with a message that names the setting. If a shift limit is not set, the Monthly Card says so and checks no limit; the hours are recorded as before. The upgrade stores the usual values (260, 12, 12) where a site had none, so nothing changes until you change them.
- **2026-11-24 — Diesel totals say when they include an estimate.** In **Equipment Diesel Consumption**, **Equipment Diesel Analysis** and the diesel box of a **Monthly Card**, the total litres are now labelled **Allocated litres (recorded + estimated)** and the cost **Diesel cost (incl. estimated)**. Recorded litres (direct fills into a machine) and estimated litres (a project-tank fill split by hours) are still shown apart. No figure changes.
- **2026-11-25 — Loads show only on cards billed per m³.** On a **Monthly Card**, the **Loads** column of the days table and the fields **Total loads**, **Total volume (m³)** and **Load volume used (m³)** now show only when the customer is billed per m³, or when the card already has loads. Other cards no longer show an empty loads column. Nothing changes in saved cards.
- **2026-11-25 — The customer statement prints on one A4 page layout.** **Equipment Customer Statement** now has an A4 print like the supplier statement. It shows each card with its dates, days, hours, the contract rate and the customer amount, additions and deductions when there are any, and the net. It does not print an hourly rate. The totals show the cards net and, when above zero, the work not yet invoiced. The PDF dialog selects this layout by default.
- **2026-11-24 — The Card Equipment accounting dimension is off until you switch it on.** **Card Settings** has a new switch, **Enable Card Equipment accounting dimension**, and it is off by default. While it is off, an upgrade or install does not create the dimension and adds no field to the accounting documents. **Equipment Supplier Statement** with an **Equipment** filter then shows a note that payments, VAT and other credits are not split by equipment. To use the dimension, a system manager takes a backup, turns the switch on and runs the one command given in the Invoicing and posting page. A site that already has the dimension keeps it, with the switch on.
- **2026-11-24 — Three more reports check who may see card amounts.** **Unbilled Card Work**, **Card Settlement Status** and **Equipment Partial Margin** now show card amounts (the card amount not invoiced, the card net) only to users whose roles may read the amounts of a **Monthly Card**. Figures that come from invoices and the ledger follow the ledger access as before. Today every role that opens these reports may read the amounts, so nothing changes for current users.
- **2026-11-24 — Internal: the party portal checks the read permission itself.** The supplier and customer portal is still switched off for every company. Its code now also checks that the user's roles may read **Monthly Cards** before it lists or opens a card. Nothing changes for users.
- **2026-11-24 — Internal: the party portal shows nothing when the user's party is not certain.** The supplier and customer portal is still switched off for every company. If two contacts carry the same email and belong to different suppliers or customers, the portal code now resolves no party instead of picking one. Nothing changes for users.
- **2026-11-24 — The summaries and the supplier statement check who may see card amounts.** **Equipment Customers Summary**, **Equipment Suppliers Summary** and **Equipment Supplier Statement** now show figures taken from card amounts only to users whose roles may read the amounts of a **Monthly Card**. This also covers the balance carried from before the period and the current due of a date-range supplier statement, because they add card work. Payments and other accounting figures follow the ledger access as before. Today every role that opens these reports may read the amounts, so nothing changes for current users.
- **2026-11-24 — A period run notices a change of loads.** Before, an approved **Card Period Run** stayed current when the loads of a per-m³ card changed but its amount did not (for example, loads moved from one day to another). A new period run now also checks the loads, total loads, total volume and load volume of each card, so such a change marks the run as changed and it must be rebuilt before posting. Period runs built before this version keep their earlier check. Cards without loads are not affected.
- **2026-11-24 — The customer statement checks who may see card amounts.** **Equipment Customer Statement** now shows rates, amounts, total volume, additions, deductions and net only to users whose roles may read the amounts of a **Monthly Card**. Today every role that opens this report may read them, so nothing changes for current users. The check protects the amounts if another role gets the report later.
- **2026-11-24 — Internal: one clear rule for which days count as billed.** Inside CARD, every place that decides whether a card day counts as billed now says on purpose whether loads count. Nothing changes for users: the supplier side still ignores loads, and the customer side and the assignment checks still count them.
- **2026-11-21 — Additions and deductions save without an Adjustment type.** When no addition/deduction types are configured in Card Settings for the card's company, the optional **Adjustment type** field is no longer shown in the table, also for users who had chosen it as a column. Enter each row with **Type** (Addition or Deduction), Side, Date, Amount and Description, and save. Where types are configured, or a row already has one, the field stays and works as before. Typing a name that is not configured is still refused, with a message that says how to fix the row.
- **2026-11-22 — The printed Monthly Card says the settlement is before VAT, and every amount in the totals shows the currency.** The settlement tables are now titled **Supplier settlement (before VAT)** and **Customer settlement (before VAT)**, because VAT is added on the invoice. In the **Card totals** box, every amount (the rate, the total amount and, for a customer card, the customer rate and amount) now prints with the currency. Amounts show two decimals (for example 3,600.00 SAR), like the settlement rows; a rate prints with the site's currency precision and is never forced to two decimals.

## v4.11.0 — 2026-11-22

Minor release on top of v4.10.1. It adds the supplier statement for a date range and payments linked to an equipment, and changes no permission or accounting rule. The upgrade adds the Card Equipment accounting dimension (empty columns on the accounting tables).

- **2026-11-22 — A payment can be linked to an equipment, and the equipment's statement deducts only its own payments.** CARD now creates the ERPNext accounting dimension **Card Equipment** by itself on upgrade, so a Journal Entry, Payment Entry or Purchase Invoice line can carry the equipment. In **Equipment Supplier Statement** with an **Equipment** filter, only the payments that carry that equipment are deducted from its balance; a supplier payment without an equipment is never deducted and is shown as **Payments not allocated to an equipment (not deducted)**. The VAT of an invoice made by CARD is split by each equipment's share of the invoice. The **Project** filter works the same way. The same rules apply to the month statement (without From/To dates). Without these filters the statement counts every supplier payment, as before. Uninstalling CARD only disables the dimension; it never deletes it or its values.
- **2026-11-22 — Supplier statement for any date range, with payments and the balance due.** In **Equipment Supplier Statement**, set **From date** and **To date** (for example 1 to 5 November) to settle a supplier every few days. The statement then counts only the card days inside those dates, also on draft cards when **Include drafts** is on, and prices them with the exact hourly rate (425 ÷ 8 = 53.125). Additions and deductions count by their own date. Below the work it lists the **payments** of those dates (submitted entries only; a draft journal entry is never counted) and shows **Balance carried from before the period**, **Net work for the period**, **Payments in the period** and **Current due to the supplier**. The VAT of purchase invoices made by CARD is added, and an invoice made by CARD is never counted twice. The printed A4 statement shows the same lines. Without the two dates the statement works as before.
- **2026-11-22 — A draft Monthly Card shows the same amount as the server.** The card form used the equipment's rounded hourly rate (53.13) while the server uses the exact rate (53.125), so a draft card could show 6,271.77 instead of 6,271.13. The form now uses the exact rate, and opening a saved card no longer marks it as changed.
- **2026-11-21 — The printed Monthly Card shows four clear totals for each side.** At the bottom of the print, each billed side (supplier, customer) has four rows: **Total before additions and deductions**, **Total additions**, **Total deductions** and **Net after additions and deductions**. The net is the amount saved on the card, so each addition and deduction counts once. Amounts print with two decimals and the currency, also when they are zero (for example `0.00 SAR`), and the net is the large bold line at the end. Cash paid rows are listed but not counted in these totals, as on the card itself. Nothing changes in saved or submitted cards.

## v4.10.1 — 2026-11-21

Patch release on top of v4.10.0. It changes no API, permission or accounting rule.

- **2026-11-21 — The Additions and deductions table shows the date for everyone, and the totals follow each row at once.** Users who had chosen their own columns for the table before v4.10.0 did not see the new **Adjustment date** column; the upgrade now adds it in front of their columns and keeps the rest of their choice. When you add, change or delete an addition or deduction, or change its side or the Cash paid tick, the card's totals change at once: **Net due** for the supplier side and **Customer net amount** for the customer side (before, only the supplier side changed, so a card rented to a customer seemed not to react until it was saved). The server still recalculates every total on save. Nothing changes on saved or submitted cards. If a row's **Adjustment type** is not one of the types configured in Card Settings, the save is still refused, and the message now tells you to clear that field and choose Addition or Deduction in **Type**.

## v4.10.0 — 2026-11-20

**v4.10.0 changes the API:** programs and Data Import files that add or change additions and deductions of a monthly card must send each row's date. After an upgrade, cash payments can be requested and approved, but **no cash payment is posted** until the posting service is set up and switched on separately.

- **2026-11-19 — The card row of a cash payment is locked.** While a cash payment of a row is pending, approved, posted or waiting for its cancellation, the row stays on the card and keeps its Cash paid tick, amount, cash account, type and side; the description and the date can still be changed. To change such a row, delete the pending payment or cancel the posted one first. This prevents the same cash from being deducted twice (once by its journal entry and again by the supplier invoice). A card cannot be cancelled while it has a cash payment that is not cancelled. An approved payment that was never posted (or whose posting failed) can now be cancelled with a reason from **Request cash cancellation**; nothing needs to be cancelled in ERPNext for it. A payment of a cancelled card is no longer approved, queued or posted, and the cancellation details of a payment can be written only by the cancellation itself.
- **2026-11-19 — The Additions and deductions table uses the full width of the card.** The table is no longer squeezed next to the totals: it now spans the form, and the totals are shown under it in a **Financial summary** section. Date, type, description, side, amount, cash paid and cash payment status are readable without scrolling on a desktop.
- **2026-11-19 — Cash payments are harder to misuse.** A cash payment can now be created only from the card (Request cash approval) or as the replacement of a cancelled payment, never directly. The person who asked for a payment, its card row, supplier, amount and cash account stay fixed. A payment is posted only when a different Card Manager approved it. A cancelled payment can be replaced once, with the same checks as a new request.
- **2026-11-18 — Cash payments are managed from the card's Additions and deductions table.** Each cash row shows its payment status (for example "Posted · Not reconciled") and its journal entry in the table. The payment actions are in the card's **Cash payments** menu: approve, queue, request cancellation and request replacement. You no longer open a separate cash payment form for these steps. A different person must approve each payment, and a replacement never posts by itself.
- **2026-11-18 — A cancelled cash payment can be replaced from the form.** A cancelled owner-paid cash payment now shows **Request replacement**. You enter a reason, the payment date and the receipt reference. The replacement waits for approval by a different Card Manager, and nothing is posted when you click. Only one live replacement can exist for a cancelled payment. Opening a Monthly Card no longer shows "Not permitted" to a Card User.
- **2026-11-16 — Additions and deductions have a date.** Each addition or deduction on a monthly card now has its own date, shown in the table and at review. The date must fall inside the card's month, and a new row takes today's date. Cards saved before this change get the first day of their month; correct it on the card if needed.
- **2026-11-15 — The CARD dashboard is redesigned.** The CARD workspace now opens with an operations dashboard: the month's financial figures (customers, suppliers, internal), the cards that need review, the monthly values chart with shortcuts under it, the links in three groups, and the latest monthly cards. The money figures are refused to users without money permission. Not released yet.
## v4.9.0 — 2026-11-15

- **2026-11-14 — Volume billing per m³ and per load.** An equipment can bill the customer per load and per cubic
  metre: loads × load volume × rate per m³, before VAT. Enter the loads on the working days of the monthly card; the
  card shows total loads, total volume and the amount. Night cards use the night rate when one is set. Hours are still
  recorded but are not billed on this basis. The monthly card print, the customer statement and a dashboard number
  card shows the new figure. Existing cards are unchanged. If a save clears loads on a non-working day, or a per-m³ card
  has hours and no loads, the form shows a message; imports and background jobs show none. See [Volume billing](/card/features/volume-billing/).
- **2026-11-15 — Review copy for unapproved cards.** An unapproved Card Monthly Card (not yet submitted) now prints as a *Review Copy — Not Approved*: one banner under the title, the workflow state, who printed it and when (site time zone), and a light *REVIEW COPY* watermark on every page. Submitted cards print exactly as before, and the generic draft label is replaced by this one. Amounts show only as before. No data, permission or print setting changes. Not released yet.

## v4.8.0 — 2026-11-14

### Packaging

- **2026-11-14 — Release page «Latest» set by SemVer (no effect on the app).** The release workflow now marks a GitHub Release as Latest only when its tag is the highest plain version number (X.Y.Z). A release published out of order no longer takes the Latest badge. Pre-release tags never do.
- **2026-11-13 — Declared Frappe version range (no behaviour change).** CARD now declares in its packaging metadata that it supports Frappe 16.55.2 up to, but not including, 17.0.0. This is packaging metadata only; it does not mean the app is published on any marketplace. Nothing changes on a running site.

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

- **2026-11-13 — Diesel tanks as Warehouses, off by default.** Groundwork is in place for a new tank-based
  diesel workflow. Each company has a new "Enable diesel tanks" switch in Card Settings → Company settings,
  which starts at **off**: nothing changes on a company that leaves it off, and the existing direct-fill
  flow (Project Diesel Fill) is untouched. When the owner turns it on for a company, a new document
  **Diesel Dispense** lets the office record litres leaving one fuel tank (an ERPNext Warehouse of type
  "Fuel Tank") to one project on one date, optionally attributed to one piece of equipment. Each submitted
  dispense creates a **draft** Stock Entry that the accountant reviews and submits — nothing is auto-posted,
  and the resulting stock movement stays at project level (never a per-equipment GL line). Cancelling the
  dispense deletes the draft Stock Entry; if the accountant has already submitted the Stock Entry, the
  dispense refuses to cancel until the Stock Entry is cancelled through ERPNext. The matching tank balance
  comes from ERPNext's standard Stock Ledger for now; the CARD-specific tank reconciliation report arrives
  in a later release.

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

- **2026-11-13 — Money amounts on the monthly card are gated by a field level.** The ten money fields on the
  monthly card (rate, total amount, additions, deductions, net due, customer rate, customer amount,
  customer net amount and the two hourly-rate snapshots) and the amount on each addition or deduction row
  now sit at field level 1. The four roles that read the monthly card today — System Manager, Card Manager,
  Card User and Accounts Manager — are the only roles granted level-1 read, so every current reader sees
  amounts exactly as before. Card Operator and the CARD Mobile portal roles are not level-1 readers; if the
  owner later grants either a monthly-card read, that role still will not see money. The monthly-card print
  hides the rate and total rows in the same case.
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
| [4.9.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.9.0.md) | 2026-11-15 | Volume billing per m³ and per load (customer side); review copy print for unapproved cards; docs and CI only otherwise |
| [4.8.0](https://github.com/SDe-ER/card/blob/main/docs/releases/v4.8.0.md) | 2026-11-14 | Big minor (43 merges): separation of duties on monthly card submit; versioned Card Period Run with accountant approval; native approval workflows (inactive by default); approval tiers; approval delegation that grants no role; money privacy on Card Monthly Card (Operator/Mobile cannot see amounts); Diesel Dispense → draft Stock Entry with tanks as Warehouses (off by default per company); per-hour rate precedence; diesel variance and fill-allocation reports; daily log mobile screens; credit note for non-taxable deductions; keep intake evidence of submitted transports; child-row cross-document guard; party portal scaffold (off by default); Marketplace packaging metadata. Every new rule is opt-in per company or warn-only — current behaviour is the default. No CARD GL write anywhere |
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
