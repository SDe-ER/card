import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, reactive } from 'vue'
import { byAttr, click, findAll, flush, mount, textOf, type TestNode } from './renderer'

// FR-150: the daily log pages mounted with their real logic; the server calls, the router and
// frappe-ui are replaced. These tests pin the page-level guards: a submitted log is never edited, a
// correction never submits anything, a failed correction is recovered, a stale save asks to reload,
// and a stop reason failure that is not a refusal is said.

const { route, router } = vi.hoisted(() => ({
  route: { name: 'DailyLogView', params: { name: 'CDL-1' } as Record<string, string>, query: {} },
  router: { replace: vi.fn(), back: vi.fn() },
}))
const reactiveRoute = reactive(route)

vi.mock('vue-router', () => ({ useRoute: () => reactiveRoute, useRouter: () => router }))

vi.mock('frappe-ui', async () => {
  const { defineComponent, h } = await import('vue')
  const Button = defineComponent({
    props: ['label', 'route', 'loading', 'disabled', 'icon', 'iconLeft', 'variant', 'size'],
    setup:
      (props, { attrs }) =>
      () =>
        h('button', { ...attrs }, props.label),
  })
  const Badge = defineComponent({
    props: ['label', 'theme', 'size'],
    setup:
      (props, { attrs }) =>
      () =>
        h('span', { ...attrs }, props.label),
  })
  const ErrorMessage = defineComponent({
    props: ['message'],
    setup:
      (props, { attrs }) =>
      () =>
        props.message ? h('div', { ...attrs, role: 'alert' }, props.message) : null,
  })
  const Field = defineComponent({
    props: ['label', 'type', 'options', 'modelValue'],
    setup:
      (props, { attrs }) =>
      () =>
        h('label', { ...attrs }, props.label ?? ''),
  })
  const LoadingIndicator = defineComponent({ setup: () => () => h('i') })
  const Dialog = defineComponent({
    props: ['open', 'title', 'message', 'actions'],
    setup: (props) => () =>
      props.open
        ? h('div', { 'data-dialog': '' }, [
            h('p', props.title),
            h('p', props.message),
            ...(props.actions ?? []).map(
              (a: { label: string; onClick?: (c: unknown) => unknown }) =>
                h(
                  'button',
                  { 'data-dialog-action': a.label, onClick: () => a.onClick?.({ close() {} }) },
                  a.label,
                ),
            ),
          ])
        : null,
  })
  return {
    Badge,
    Button,
    Dialog,
    ErrorMessage,
    FormControl: Field,
    LoadingIndicator,
    TextInput: Field,
  }
})

vi.mock('../data/session', () => ({ getSessionContext: vi.fn() }))
vi.mock('../data/needs', () => ({ getPortal: vi.fn() }))
vi.mock('../data/dailyLog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../data/dailyLog')>()),
  amendmentOf: vi.fn(),
  correctLog: vi.fn(),
  createCorrectedDraft: vi.fn(),
  createLog: vi.fn(),
  getLog: vi.fn(),
  listMyLogs: vi.fn(),
  stopReasons: vi.fn(),
  submitLog: vi.fn(),
  updateLog: vi.fn(),
}))

import { ApiError } from '../data/api'
import * as data from '../data/dailyLog'
import { getPortal } from '../data/needs'
import { getSessionContext } from '../data/session'
import { __ } from '../i18n'
import DailyLogForm from '../pages/DailyLogForm.vue'
import DailyLogList from '../pages/DailyLogList.vue'
import DailyLogView from '../pages/DailyLogView.vue'

const m = vi.mocked(data)
const RouterLink = defineComponent({
  props: ['to'],
  setup:
    (_, { slots, attrs }) =>
    () =>
      h('a', attrs, slots.default?.()),
})

function open(page: Parameters<typeof mount>[0]) {
  return mount(page, (app) => {
    app.config.globalProperties.__ = __
    app.component('RouterLink', RouterLink)
  })
}

function log(overrides: Partial<data.DailyLog> = {}): data.DailyLog {
  return {
    name: 'CDL-1',
    company: 'Test Company',
    project: 'PROJ-A',
    log_date: '2026-11-09',
    notes: '',
    docstatus: 1,
    approval_status: 'Returned for correction',
    return_reason: 'Day hours too high',
    modified: '2026-11-09 10:00:00',
    rows: [
      {
        name: 'r1',
        equipment: 'CEQ-1',
        equipment_name: 'Loader 1',
        day_hours: 9,
        night_hours: 0,
        stopped_hours: 1,
        stop_reason: 'Breakdown - TC',
        notes: '',
      },
    ],
    ...overrides,
  }
}

const stale = () =>
  new ApiError(
    'Error: Document has been modified after you have opened it (2026-11-09 10:00:00, 2026-11-09 10:05:00). Please refresh to get the latest document.',
    417,
    'TimestampMismatchError',
  )

const action = (root: TestNode, name: string) => byAttr(root, 'data-action', name)
const dialogButton = (root: TestNode, label: string) => {
  const [button] = byAttr(root, 'data-dialog-action', label)
  if (!button) throw new Error(`no dialog button ${label}`)
  return button
}

beforeEach(() => {
  vi.clearAllMocks()
  reactiveRoute.name = 'DailyLogView'
  reactiveRoute.params = { name: 'CDL-1' }
  reactiveRoute.query = {}
  vi.mocked(getSessionContext).mockResolvedValue({
    user: 'op@example.com',
    full_name: 'Op',
    roles: ['Card Operator'],
    employee: { name: 'E1', employee_name: 'Op', company: 'Test Company' },
    catalog_only: false,
    card_version: '4.7.0',
  })
  vi.mocked(getPortal).mockResolvedValue({
    employee: 'E1',
    allowed: true,
    machines: [{ name: 'CEQ-1', equipment_name: 'Loader 1', project: 'PROJ-A' }],
    requests: [],
  })
  m.stopReasons.mockResolvedValue(null)
  m.amendmentOf.mockResolvedValue(null)
})

describe('DailyLogView: correction', () => {
  it('corrects a returned log and never submits anything', async () => {
    m.getLog.mockResolvedValue(log())
    m.correctLog.mockResolvedValue(log({ name: 'CDL-1-1', docstatus: 0 }))
    const { root } = await open(DailyLogView)
    await click(action(root, 'correct')[0])
    await click(dialogButton(root, 'Correct this daily log'))
    expect(m.correctLog).toHaveBeenCalledTimes(1)
    expect(m.submitLog).not.toHaveBeenCalled()
    expect(router.replace).toHaveBeenCalledWith({
      name: 'DailyLogEdit',
      params: { name: 'CDL-1-1' },
    })
  })

  it('recovers when the corrected draft could not be created', async () => {
    m.getLog.mockResolvedValueOnce(log())
    m.correctLog.mockRejectedValue(new ApiError('Period is locked', 417, 'ValidationError'))
    // read again after the failure: cancelled, still returned, nothing amends it
    m.getLog.mockResolvedValue(log({ docstatus: 2 }))
    const { root, text } = await open(DailyLogView)
    await click(action(root, 'correct')[0])
    await click(dialogButton(root, 'Correct this daily log'))
    expect(text()).toContain('Period is locked')
    expect(byAttr(root, 'data-state', 'CorrectionDue')).toHaveLength(1)
    expect(byAttr(root, 'data-testid', 'correction-due')).toHaveLength(1)
    expect(action(root, 'correct')).toHaveLength(0)
    // "Create corrected draft": the amendment only
    m.createCorrectedDraft.mockResolvedValue(log({ name: 'CDL-1-1', docstatus: 0 }))
    await click(action(root, 'recreate')[0])
    await click(dialogButton(root, 'Create corrected draft'))
    expect(m.createCorrectedDraft).toHaveBeenCalledTimes(1)
    expect(m.correctLog).toHaveBeenCalledTimes(1)
    expect(m.submitLog).not.toHaveBeenCalled()
    expect(router.replace).toHaveBeenCalledWith({
      name: 'DailyLogEdit',
      params: { name: 'CDL-1-1' },
    })
  })

  it('offers nothing on a cancelled returned log that was already corrected', async () => {
    m.getLog.mockResolvedValue(log({ docstatus: 2 }))
    m.amendmentOf.mockResolvedValue({
      name: 'CDL-1-1',
      docstatus: 0,
      approval_status: 'Pending',
    } as data.DailyLogSummary)
    const { root } = await open(DailyLogView)
    expect(m.amendmentOf).toHaveBeenCalledWith('CDL-1')
    expect(action(root, 'recreate')).toHaveLength(0)
    expect(byAttr(root, 'data-state', 'Cancelled')).toHaveLength(1)
  })

  it('offers nothing when the amendment check fails', async () => {
    m.getLog.mockResolvedValue(log({ docstatus: 2 }))
    m.amendmentOf.mockRejectedValue(new TypeError('Failed to fetch'))
    const { root } = await open(DailyLogView)
    expect(action(root, 'recreate')).toHaveLength(0)
  })

  it('opens the existing correction when one was created meanwhile', async () => {
    m.getLog.mockResolvedValue(log({ docstatus: 2 }))
    const existing = { name: 'CDL-1-1', docstatus: 0 } as data.DailyLogSummary
    m.createCorrectedDraft.mockRejectedValue(new data.AmendmentExistsError(existing))
    const { root } = await open(DailyLogView)
    await click(action(root, 'recreate')[0])
    await click(dialogButton(root, 'Create corrected draft'))
    expect(router.replace).toHaveBeenCalledWith({
      name: 'DailyLogView',
      params: { name: 'CDL-1-1' },
    })
  })
})

describe('stale saves', () => {
  it('view: a stale submit asks to reload, without the raw server text', async () => {
    m.getLog.mockResolvedValue(log({ docstatus: 0, approval_status: 'Pending' }))
    m.submitLog.mockRejectedValue(stale())
    const { root, text } = await open(DailyLogView)
    await click(action(root, 'submit')[0])
    await click(dialogButton(root, 'Send to supervisor'))
    expect(byAttr(root, 'data-testid', 'stale')).toHaveLength(1)
    expect(text()).not.toContain('2026-11-09 10:05:00')
    const calls = m.getLog.mock.calls.length
    await click(action(root, 'reload')[0])
    expect(m.getLog.mock.calls.length).toBe(calls + 1)
    expect(byAttr(root, 'data-testid', 'stale')).toHaveLength(0)
  })

  it('form: a stale save asks to reload and reloads the stored log', async () => {
    reactiveRoute.name = 'DailyLogEdit'
    m.getLog
      .mockResolvedValueOnce(log({ docstatus: 0, approval_status: 'Pending', notes: 'old' }))
      .mockResolvedValueOnce(log({ docstatus: 0, approval_status: 'Pending', notes: 'newer' }))
    m.updateLog.mockRejectedValue(stale())
    const { root, text } = await open(DailyLogForm)
    const [form] = findAll(root, (n) => n.tag === 'form')
    await (form.props.onSubmit as (e: unknown) => Promise<void>)({ preventDefault() {} })
    await flush()
    expect(m.updateLog).toHaveBeenCalledTimes(1)
    expect(byAttr(root, 'data-testid', 'stale')).toHaveLength(1)
    expect(text()).not.toContain('2026-11-09 10:05:00')
    await click(action(root, 'reload')[0])
    expect(m.getLog).toHaveBeenCalledTimes(2)
    expect(byAttr(root, 'data-testid', 'stale')).toHaveLength(0)
  })
})

describe('DailyLogForm guards', () => {
  it('never shows the form for a submitted log', async () => {
    reactiveRoute.name = 'DailyLogEdit'
    m.getLog.mockResolvedValue(log({ approval_status: 'Pending' }))
    const { root, text } = await open(DailyLogForm)
    expect(byAttr(root, 'data-testid', 'locked')).toHaveLength(1)
    expect(findAll(root, (n) => n.tag === 'form')).toHaveLength(0)
    expect(text()).not.toContain('Save draft')
    expect(m.updateLog).not.toHaveBeenCalled()
  })

  it('says when the stop reasons could not be read (not a refusal)', async () => {
    m.stopReasons.mockRejectedValue(new ApiError('HTTP 500', 500))
    reactiveRoute.name = 'DailyLogNew'
    const { root } = await open(DailyLogForm)
    expect(byAttr(root, 'data-testid', 'reasons-failed')).toHaveLength(1)
  })

  it('shows no picker and no warning when the server refuses them (operator)', async () => {
    reactiveRoute.name = 'DailyLogEdit'
    m.getLog.mockResolvedValue(log({ docstatus: 0, approval_status: 'Pending' }))
    m.stopReasons.mockResolvedValue(null)
    const { root, text } = await open(DailyLogForm)
    expect(byAttr(root, 'data-testid', 'reasons-failed')).toHaveLength(0)
    // the stored reason is shown by its readable name, not its record name
    const [stored] = byAttr(root, 'data-testid', 'stored-reason')
    expect(textOf(stored)).toContain('Breakdown')
    expect(text()).not.toContain('Breakdown - TC')
  })
})

describe('DailyLogList', () => {
  it('marks a log whose corrected draft is missing', async () => {
    m.listMyLogs.mockResolvedValue([
      { ...log({ docstatus: 2 }), correction_due: true },
      { ...log({ name: 'CDL-2', docstatus: 0, approval_status: 'Pending' }) },
    ])
    const { root, text } = await open(DailyLogList)
    expect(byAttr(root, 'data-state', 'CorrectionDue')).toHaveLength(1)
    expect(byAttr(root, 'data-state', 'Draft')).toHaveLength(1)
    expect(text()).toContain('Corrected draft missing')
  })
})
