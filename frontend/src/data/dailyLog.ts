import { ApiError, getResource, insertResource, listResource, updateResource } from './api'
import { __ } from '../i18n'

// FR-150: CARD Mobile screens for the Card Daily Log (FR-142, card/daily_log.py). Only Frappe's
// standard REST routes under the user's own permissions; no CARD endpoint was added. The server
// decides who may do what: the operator (Card Operator, `if_owner`) reads and writes his own logs,
// the company scope applies, and every approval field is written by the server only. This module
// therefore sends only the fields an operator enters (allowlists below): never an approval, editor,
// preparer or status field. A daily log has no money field; none is read or shown (O-20).

export const DOCTYPE = 'Card Daily Log'

export const PENDING = 'Pending'
export const VERIFIED = 'Verified by supervisor'
export const APPROVED = 'Approved'
export const RETURNED = 'Returned for correction'

// header fields the screens send: `company` on a new log only
export const HEADER_FIELDS = ['project', 'log_date', 'notes'] as const
// row fields the screens send back. The stop reason and the responsible party are kept as stored
// (an operator cannot read the stop reasons; a supervisor can pick one), so a save never clears them.
export const ROW_FIELDS = [
  'name',
  'equipment',
  'day_hours',
  'night_hours',
  'stopped_hours',
  'stop_reason',
  'responsible_party_type',
  'responsible_party',
  'responsible_party_name',
  'notes',
] as const

// written by the server only (card.daily_log.APPROVAL_FIELDS and SERVER_FIELDS); never sent
export const SERVER_FIELDS = [
  'approval_status',
  'approved_by',
  'approved_on',
  'self_approved',
  'return_reason',
  'returned_by',
  'returned_on',
  'verified_by',
  'verified_on',
  'submitted_by',
  'edited_by',
  'supervisor',
  'owner',
] as const

// what the list asks for: no money, no preparer (`amended_from` finds the logs already corrected)
export const LIST_FIELDS = [
  'name',
  'project',
  'log_date',
  'approval_status',
  'docstatus',
  'modified',
  'amended_from',
] as const

export interface DailyLogRow {
  name?: string
  equipment: string
  equipment_name?: string | null
  day_hours: number | null
  night_hours: number | null
  stopped_hours: number | null
  stop_reason?: string | null
  responsible_party_type?: string | null
  responsible_party?: string | null
  responsible_party_name?: string | null
  notes?: string | null
}

export interface DailyLog {
  name: string
  company: string
  project: string
  log_date: string
  notes?: string | null
  docstatus: number
  approval_status: string | null
  return_reason?: string | null
  modified?: string
  amended_from?: string | null
  rows: DailyLogRow[]
}

export type DailyLogSummary = Pick<
  DailyLog,
  'name' | 'project' | 'log_date' | 'approval_status' | 'docstatus' | 'modified' | 'amended_from'
> & {
  // a cancelled returned log whose corrected draft was never created (see needsCorrection)
  correction_due?: boolean
}

export interface DraftLog {
  project: string
  log_date: string
  notes: string
  rows: DailyLogRow[]
}

// ---------- state and actions ----------
export type LogState = 'Draft' | 'Pending' | 'Verified' | 'Approved' | 'Returned' | 'Cancelled'

export function logState(log: Pick<DailyLog, 'docstatus' | 'approval_status'>): LogState {
  if (log.docstatus === 2) return 'Cancelled'
  if (log.docstatus !== 1) return 'Draft'
  if (log.approval_status === APPROVED) return 'Approved'
  if (log.approval_status === RETURNED) return 'Returned'
  if (log.approval_status === VERIFIED) return 'Verified'
  return 'Pending'
}

export function stateLabel(state: LogState): string {
  if (state === 'Draft') return __('Draft', [], 'Card Mobile')
  if (state === 'Pending') return __('Pending', [], 'Card Mobile')
  if (state === 'Verified') return __(VERIFIED)
  if (state === 'Approved') return __('Approved', [], 'Card Mobile')
  if (state === 'Returned') return __(RETURNED)
  return __('Cancelled', [], 'Card Mobile')
}

export function stateTheme(state: LogState): 'gray' | 'blue' | 'green' | 'amber' | 'red' {
  return (
    (
      {
        Draft: 'gray',
        Pending: 'amber',
        Verified: 'blue',
        Approved: 'green',
        Returned: 'red',
      } as const
    )[state as 'Draft'] ?? 'gray'
  )
}

// The actions CARD Mobile offers. Approving, verifying and returning are not among them for any role:
// supervisors and managers do that in CARD Desk, where the server checks the separation of duties.
// The server still checks every action offered here.
export type LogAction = 'edit' | 'submit' | 'correct' | 'recreate' | 'desk'

export const REVIEW_ROLES = ['Card Supervisor', 'Card Manager', 'System Manager']

// A correction is two requests (cancel, then the amending draft). When the second one failed, the log
// is cancelled and still "Returned for correction" with no amendment: it needs its corrected draft.
// `amended` is whether any log amends it (unknown = undefined: nothing is offered).
export function needsCorrection(
  log: Pick<DailyLog, 'docstatus' | 'approval_status'>,
  amended: boolean | undefined,
): boolean {
  return log.docstatus === 2 && log.approval_status === RETURNED && amended === false
}

export function actionsFor(
  log: Pick<DailyLog, 'docstatus' | 'approval_status'>,
  roles: string[],
  amended?: boolean,
): LogAction[] {
  const state = logState(log)
  const reviewer = roles.some((r) => REVIEW_ROLES.includes(r))
  const actions: LogAction[] = []
  if (state === 'Draft') actions.push('edit', 'submit')
  // returned: cancel it and open a corrected draft (Frappe cancel and amend, checked by the server)
  if (state === 'Returned') actions.push('correct')
  // the cancel went through but the corrected draft was not created: create it now
  if (needsCorrection(log, amended)) actions.push('recreate')
  if (reviewer && state !== 'Draft' && state !== 'Cancelled') actions.push('desk')
  return actions
}

// Frappe refuses a save over a newer version of the log (the `modified` stamp sent with it)
export function isStale(e: unknown): boolean {
  return e instanceof ApiError && e.excType === 'TimestampMismatchError'
}

// The readable part of a stop reason's record name. CARD names a reason "<reason name> - <company
// abbreviation>" (card_stop_reason.reason_docname); an operator may not read the reason itself, so
// the label comes from the name he already has. A name of another shape is shown as it is.
export function stopReasonLabel(name: string | null | undefined, reasons?: StopReason[] | null) {
  if (!name) return ''
  const known = reasons?.find((r) => r.name === name)
  if (known?.reason_name) return known.reason_name
  const cut = name.lastIndexOf(' - ')
  return cut > 0 ? name.slice(0, cut) : name
}

// ---------- payloads ----------
function num(value: unknown): number {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? n : 0
}

function text(value: unknown): string | null {
  const s = typeof value === 'string' ? value.trim() : ''
  return s || null
}

export function rowPayload(row: DailyLogRow): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const field of ROW_FIELDS) {
    if (field === 'day_hours' || field === 'night_hours' || field === 'stopped_hours') {
      out[field] = num(row[field])
    } else if (field === 'name') {
      if (row.name) out.name = row.name
    } else if (field === 'notes') {
      out.notes = text(row.notes)
    } else {
      out[field] = row[field] ?? null
    }
  }
  return out
}

export function draftPayload(draft: DraftLog): Record<string, unknown> {
  return {
    project: draft.project,
    log_date: draft.log_date,
    notes: text(draft.notes),
    rows: draft.rows.map(rowPayload),
  }
}

// a row the operator must fix before saving (1-based numbers, for the message)
export function invalidRows(rows: DailyLogRow[]): number[] {
  return rows.flatMap((r, i) => {
    const values = [r.day_hours, r.night_hours, r.stopped_hours].map((v) => Number(v ?? 0))
    const bad = !r.equipment || values.some((v) => !Number.isFinite(v) || v < 0)
    const total = values.reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0)
    return bad || total > 24 ? [i + 1] : []
  })
}

export function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// ---------- the operator's machines (card.materials.get_portal_context) ----------
export interface LogMachine {
  name: string
  equipment_name: string | null
  project: string | null
}

// the projects his machines are on now, plus the log's own project when editing
export function projectOptions(machines: LogMachine[], current?: string | null) {
  const projects = new Set(machines.map((m) => m.project).filter((p): p is string => !!p))
  if (current) projects.add(current)
  return [...projects].sort().map((p) => ({ label: p, value: p }))
}

export function machinesOn(project: string, machines: LogMachine[]): LogMachine[] {
  return machines.filter((m) => m.project === project)
}

export function newRow(machine: LogMachine): DailyLogRow {
  return {
    equipment: machine.name,
    equipment_name: machine.equipment_name,
    day_hours: null,
    night_hours: null,
    stopped_hours: null,
    stop_reason: null,
    notes: '',
  }
}

// ---------- errors ----------
// Frappe's own message when the server answered; a plain sentence when it could not be reached.
export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof TypeError)
    return __(
      'The server could not be reached. Check the connection and try again.',
      [],
      'Card Mobile',
    )
  return (e as Error)?.message || __('Something went wrong. Try again.', [], 'Card Mobile')
}

// ---------- calls (standard REST, the user's own permissions) ----------
// The user's live logs, plus his cancelled returned logs that no log amends (a correction whose
// second request failed), so he can still create the corrected draft. Cancelled logs that were
// corrected stay hidden: their amendment is listed instead.
export async function listMyLogs(user: string): Promise<DailyLogSummary[]> {
  const [live, cancelled] = await Promise.all([
    listResource<DailyLogSummary>(DOCTYPE, {
      fields: [...LIST_FIELDS],
      filters: [
        ['owner', '=', user],
        ['docstatus', '<', 2],
      ],
      order_by: 'log_date desc, creation desc',
      limit: 50,
    }),
    listResource<DailyLogSummary>(DOCTYPE, {
      fields: [...LIST_FIELDS],
      filters: [
        ['owner', '=', user],
        ['docstatus', '=', 2],
      ],
      order_by: 'log_date desc, creation desc',
      limit: 100,
    }),
  ])
  const amended = new Set(
    [...live, ...cancelled].map((l) => l.amended_from).filter((n): n is string => !!n),
  )
  const due = cancelled
    .filter((l) => needsCorrection(l, amended.has(l.name)))
    .map((l) => ({ ...l, correction_due: true }))
  return [...due, ...live].sort((a, b) => (a.log_date < b.log_date ? 1 : -1))
}

// The log that amends this one, if the server lets the user see one (his own logs; any state). A
// second amendment would also take the same name (Frappe names it <log>-1) and be refused.
export async function amendmentOf(name: string): Promise<DailyLogSummary | null> {
  const found = await listResource<DailyLogSummary>(DOCTYPE, {
    fields: ['name', 'docstatus', 'approval_status'],
    filters: [['amended_from', '=', name]],
    limit: 1,
  })
  return found[0] ?? null
}

export class AmendmentExistsError extends Error {
  amendment: DailyLogSummary
  constructor(amendment: DailyLogSummary) {
    super(__('This daily log was already corrected: {0}', [amendment.name]))
    this.amendment = amendment
  }
}

export function getLog(name: string): Promise<DailyLog> {
  return getResource<DailyLog>(DOCTYPE, name)
}

export function createLog(company: string, draft: DraftLog, amendedFrom?: string) {
  const data: Record<string, unknown> = { company, ...draftPayload(draft) }
  if (amendedFrom) data.amended_from = amendedFrom
  return insertResource<DailyLog>(DOCTYPE, data)
}

// `modified` makes the server refuse a save over a newer version (TimestampMismatchError)
export function updateLog(log: Pick<DailyLog, 'name' | 'modified'>, draft: DraftLog) {
  return updateResource<DailyLog>(DOCTYPE, log.name, {
    ...draftPayload(draft),
    modified: log.modified,
  })
}

// Submit for the supervisor: only the docstatus changes; the server submits the stored log.
export function submitLog(log: Pick<DailyLog, 'name' | 'modified'>) {
  return updateResource<DailyLog>(DOCTYPE, log.name, { docstatus: 1, modified: log.modified })
}

export interface StopReason {
  name: string
  reason_name: string
}

// The enabled stop reasons of the company, for users who may read them (supervisors). An operator
// has no read permission on Card Stop Reason: the server refuses, and the picker is not shown
// (null); his stopped hours and notes are kept and the supervisor names the reason.
export async function stopReasons(company: string): Promise<StopReason[] | null> {
  try {
    return await listResource<StopReason>('Card Stop Reason', {
      fields: ['name', 'reason_name'],
      filters: [
        ['company', '=', company],
        ['enabled', '=', 1],
      ],
      order_by: 'reason_name asc',
      limit: 100,
    })
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) return null
    throw e
  }
}

export function draftFrom(log: DailyLog): DraftLog {
  return {
    project: log.project,
    log_date: log.log_date,
    notes: log.notes || '',
    rows: log.rows.map((r) => ({ ...r })),
  }
}

// The corrected draft of a cancelled returned log: a new log that amends it, with the same header
// and rows (no row names). It is created only when no amendment exists (checked on the server
// first); Frappe's name for a second amendment and the duplicate-entry guard refuse it anyway.
export async function createCorrectedDraft(log: DailyLog): Promise<DailyLog> {
  const existing = await amendmentOf(log.name)
  if (existing) throw new AmendmentExistsError(existing)
  const draft = draftFrom(log)
  draft.rows = draft.rows.map(({ name: _name, ...row }) => row)
  return createLog(log.company, draft, log.name)
}

// A returned log, corrected in two requests: 1. cancel it (only the docstatus is sent; the server
// keeps every stored field); 2. create the corrected draft. When step 2 fails, the log stays
// cancelled and "My daily logs" offers "Create corrected draft" for it (createCorrectedDraft).
export async function correctLog(log: DailyLog): Promise<DailyLog> {
  await updateResource<DailyLog>(DOCTYPE, log.name, { docstatus: 2, modified: log.modified })
  return createCorrectedDraft({ ...log, docstatus: 2 })
}
