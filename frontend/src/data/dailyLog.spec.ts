import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import {
  actionsFor,
  correctLog,
  createLog,
  draftPayload,
  errorText,
  invalidRows,
  LIST_FIELDS,
  listMyLogs,
  logState,
  machinesOn,
  projectOptions,
  ROW_FIELDS,
  SERVER_FIELDS,
  stopReasons,
  submitLog,
  updateLog,
  type DailyLog,
  type DraftLog,
} from './dailyLog'

// FR-150: the CARD Mobile daily log calls. The server decides every permission; these tests pin
// that the screens offer no approval, and send no approval, editor, preparer or money field.

const ROLES = {
  operator: ['Card Operator'],
  supervisor: ['Card Supervisor'],
  manager: ['Card Manager'],
  all: ['Card Operator', 'Card Supervisor', 'Card Manager', 'System Manager'],
}
const STATES: [number, string | null][] = [
  [0, 'Pending'],
  [0, null],
  [1, 'Pending'],
  [1, 'Verified by supervisor'],
  [1, 'Approved'],
  [1, 'Returned for correction'],
  [2, 'Pending'],
]
const APPROVAL_ACTION = /approv|verif|return|reject/i
const MONEY = /rate|amount|price|cost|value|total|currency|billing/i

function storedLog(overrides: Partial<DailyLog> = {}): DailyLog {
  return {
    name: 'CDL-00001',
    company: 'Test Company',
    project: 'PROJ-A',
    log_date: '2026-11-09',
    notes: 'night shift short',
    docstatus: 1,
    approval_status: 'Returned for correction',
    return_reason: 'wrong hours',
    modified: '2026-11-09 10:00:00.000000',
    rows: [
      {
        name: 'row1',
        equipment: 'CEQ-0001',
        equipment_name: 'Loader 1',
        day_hours: 9,
        night_hours: 0,
        stopped_hours: 1,
        stop_reason: 'SR-1',
        responsible_party_type: 'Company',
        responsible_party: 'Test Company',
        responsible_party_name: null,
        notes: '',
      },
    ],
    ...overrides,
  }
}

// a log as a client might hold it after reading it: every server field filled in
function forgedDraft(): DraftLog {
  const row = {
    ...storedLog().rows[0],
    approval_status: 'Approved',
    approved_by: 'boss@example.com',
    rate: 100,
    amount: 900,
  }
  return {
    project: 'PROJ-A',
    log_date: '2026-11-09',
    notes: ' ',
    rows: [row],
    ...{ approval_status: 'Approved', submitted_by: 'x', edited_by: 'x', rate: 5 },
  } as DraftLog
}

function sentKeys(body: Record<string, unknown>): string[] {
  const rows = (body.rows as Record<string, unknown>[] | undefined) ?? []
  return [...Object.keys(body), ...rows.flatMap((r) => Object.keys(r))]
}

describe('logState and actionsFor', () => {
  it('offers edit and submit on a draft, correct on a returned log, nothing else', () => {
    expect(actionsFor({ docstatus: 0, approval_status: 'Pending' }, ROLES.operator)).toEqual([
      'edit',
      'submit',
    ])
    expect(actionsFor({ docstatus: 1, approval_status: 'Pending' }, ROLES.operator)).toEqual([])
    expect(
      actionsFor({ docstatus: 1, approval_status: 'Verified by supervisor' }, ROLES.operator),
    ).toEqual([])
    expect(actionsFor({ docstatus: 1, approval_status: 'Approved' }, ROLES.operator)).toEqual([])
    expect(
      actionsFor({ docstatus: 1, approval_status: 'Returned for correction' }, ROLES.operator),
    ).toEqual(['correct'])
    expect(actionsFor({ docstatus: 2, approval_status: 'Pending' }, ROLES.operator)).toEqual([])
  })

  it('gives reviewers only a link to CARD Desk on a submitted log', () => {
    for (const roles of [ROLES.supervisor, ROLES.manager, ROLES.all]) {
      expect(actionsFor({ docstatus: 1, approval_status: 'Pending' }, roles)).toEqual(['desk'])
      expect(actionsFor({ docstatus: 0, approval_status: 'Pending' }, roles)).toEqual([
        'edit',
        'submit',
      ])
      expect(actionsFor({ docstatus: 2, approval_status: 'Approved' }, roles)).toEqual([])
    }
  })

  it('never offers an approval action, for any role and state', () => {
    for (const roles of Object.values(ROLES)) {
      for (const [docstatus, approval_status] of STATES) {
        const actions = actionsFor({ docstatus, approval_status }, roles)
        expect(actions.filter((a) => APPROVAL_ACTION.test(a))).toEqual([])
      }
    }
  })

  it('reads the state from docstatus first: a draft is a draft whatever its status says', () => {
    expect(logState({ docstatus: 0, approval_status: 'Approved' })).toBe('Draft')
    expect(logState({ docstatus: 1, approval_status: null })).toBe('Pending')
    expect(logState({ docstatus: 2, approval_status: 'Approved' })).toBe('Cancelled')
  })
})

describe('payloads', () => {
  it('sends only the operator fields: no approval, editor, preparer or money field', () => {
    const body = draftPayload(forgedDraft())
    const keys = sentKeys(body)
    for (const field of SERVER_FIELDS) expect(keys).not.toContain(field)
    expect(keys.filter((k) => MONEY.test(k))).toEqual([])
    expect(Object.keys(body).sort()).toEqual(['log_date', 'notes', 'project', 'rows'])
    expect(Object.keys((body.rows as object[])[0]).sort()).toEqual([...ROW_FIELDS].sort())
  })

  it('keeps the stored stop reason and responsible party of a row (a save never clears them)', () => {
    const [row] = draftPayload(forgedDraft()).rows as Record<string, unknown>[]
    expect(row).toMatchObject({
      name: 'row1',
      stop_reason: 'SR-1',
      responsible_party_type: 'Company',
      responsible_party: 'Test Company',
    })
  })

  it('sends empty or negative hours as 0 and empty notes as nothing', () => {
    const draft: DraftLog = {
      project: 'P',
      log_date: '2026-11-09',
      notes: '  ',
      rows: [{ equipment: 'E', day_hours: null, night_hours: -2, stopped_hours: 3.5, notes: ' ' }],
    }
    const body = draftPayload(draft)
    expect(body.notes).toBeNull()
    expect((body.rows as Record<string, unknown>[])[0]).toMatchObject({
      day_hours: 0,
      night_hours: 0,
      stopped_hours: 3.5,
      notes: null,
    })
  })

  it('asks the list for no money and no preparer field', () => {
    expect(LIST_FIELDS.filter((f) => MONEY.test(f))).toEqual([])
    for (const field of SERVER_FIELDS.filter((f) => f !== 'approval_status'))
      expect(LIST_FIELDS).not.toContain(field)
  })

  it('names the rows to fix before saving', () => {
    expect(
      invalidRows([
        { equipment: 'A', day_hours: 10, night_hours: 10, stopped_hours: 4 },
        { equipment: 'B', day_hours: 10, night_hours: 10, stopped_hours: 5 },
        { equipment: 'C', day_hours: -1, night_hours: null, stopped_hours: null },
        { equipment: '', day_hours: 1, night_hours: null, stopped_hours: null },
      ]),
    ).toEqual([2, 3, 4])
  })
})

describe('machines', () => {
  const machines = [
    { name: 'E1', equipment_name: 'Loader', project: 'P2' },
    { name: 'E2', equipment_name: 'Crusher', project: 'P1' },
    { name: 'E3', equipment_name: 'Yard truck', project: null },
    { name: 'E4', equipment_name: 'Grader', project: 'P1' },
  ]
  it('offers the projects his machines are on, and the log project when editing', () => {
    expect(projectOptions(machines).map((o) => o.value)).toEqual(['P1', 'P2'])
    expect(projectOptions(machines, 'P9').map((o) => o.value)).toEqual(['P1', 'P2', 'P9'])
    expect(machinesOn('P1', machines).map((m) => m.name)).toEqual(['E2', 'E4'])
  })
})

describe('REST calls', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  function reply(status: number, body: unknown) {
    return Promise.resolve(new Response(JSON.stringify(body), { status }))
  }
  function call(i: number) {
    const [url, init] = fetchMock.mock.calls[i] as [string, RequestInit | undefined]
    return {
      url: decodeURIComponent(url),
      method: init?.method ?? 'GET',
      body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null,
    }
  }

  beforeEach(() => {
    fetchMock = vi.fn(() => reply(200, { data: storedLog({ name: 'CDL-00001-1' }) }))
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('window', { csrf_token: 'tok', location: { replace: vi.fn(), reload: vi.fn() } })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('lists only the user own, not cancelled logs, with the list fields', async () => {
    fetchMock.mockImplementationOnce(() => reply(200, { data: [] }))
    await listMyLogs('op@example.com')
    const { url, method } = call(0)
    expect(method).toBe('GET')
    expect(url).toContain('/api/resource/Card Daily Log?')
    const query = new URLSearchParams(url.split('?')[1])
    expect(JSON.parse(query.get('fields')!)).toEqual([...LIST_FIELDS])
    expect(JSON.parse(query.get('filters')!)).toEqual([
      ['owner', '=', 'op@example.com'],
      ['docstatus', '<', 2],
    ])
  })

  it('creates a draft with the company and the operator fields only', async () => {
    await createLog('Test Company', forgedDraft())
    const { url, method, body } = call(0)
    expect([method, url]).toEqual(['POST', '/api/resource/Card Daily Log'])
    expect(body?.company).toBe('Test Company')
    expect(body).not.toHaveProperty('docstatus')
    for (const field of SERVER_FIELDS) expect(sentKeys(body!)).not.toContain(field)
  })

  it('saves a draft with its modified stamp, so a newer version is not overwritten', async () => {
    await updateLog(storedLog({ docstatus: 0 }), forgedDraft())
    const { url, method, body } = call(0)
    expect([method, url]).toEqual(['PUT', '/api/resource/Card Daily Log/CDL-00001'])
    expect(body?.modified).toBe('2026-11-09 10:00:00.000000')
    expect(body).not.toHaveProperty('company')
    for (const field of SERVER_FIELDS) expect(sentKeys(body!)).not.toContain(field)
  })

  it('submits by changing the docstatus only', async () => {
    await submitLog(storedLog({ docstatus: 0 }))
    expect(call(0).body).toEqual({ docstatus: 1, modified: '2026-11-09 10:00:00.000000' })
  })

  it('corrects a returned log: cancel with the docstatus only, then an amending draft', async () => {
    const created = await correctLog(storedLog())
    expect(created.name).toBe('CDL-00001-1')
    const cancel = call(0)
    expect([cancel.method, cancel.url]).toEqual(['PUT', '/api/resource/Card Daily Log/CDL-00001'])
    expect(cancel.body).toEqual({ docstatus: 2, modified: '2026-11-09 10:00:00.000000' })
    const insert = call(1)
    expect(insert.method).toBe('POST')
    expect(insert.body).toMatchObject({ company: 'Test Company', amended_from: 'CDL-00001' })
    const rows = insert.body!.rows as Record<string, unknown>[]
    expect(rows[0]).not.toHaveProperty('name')
    expect(rows[0]).toMatchObject({ equipment: 'CEQ-0001', day_hours: 9, stopped_hours: 1 })
    for (const field of SERVER_FIELDS) expect(sentKeys(insert.body!)).not.toContain(field)
  })

  it('does not create the amendment when the cancel is refused', async () => {
    fetchMock.mockImplementationOnce(() =>
      reply(403, {
        exc_type: 'PermissionError',
        _server_messages: JSON.stringify([JSON.stringify({ message: 'Not permitted' })]),
      }),
    )
    vi.stubGlobal('document', { cookie: 'user_id=op%40example.com' })
    await expect(correctLog(storedLog())).rejects.toThrow('Not permitted')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('hides the stop reason picker when the server refuses the stop reasons (operator)', async () => {
    vi.stubGlobal('document', { cookie: 'user_id=op%40example.com' })
    fetchMock.mockImplementationOnce(() => reply(403, { exc_type: 'PermissionError' }))
    await expect(stopReasons('Test Company')).resolves.toBeNull()
    fetchMock.mockImplementationOnce(() =>
      reply(200, { data: [{ name: 'SR-1', reason_name: 'Breakdown' }] }),
    )
    await expect(stopReasons('Test Company')).resolves.toEqual([
      { name: 'SR-1', reason_name: 'Breakdown' },
    ])
    const query = new URLSearchParams(call(1).url.split('?')[1])
    expect(JSON.parse(query.get('filters')!)).toEqual([
      ['company', '=', 'Test Company'],
      ['enabled', '=', 1],
    ])
  })
})

describe('errorText', () => {
  it("shows the server's own message", async () => {
    const body = {
      exc_type: 'ValidationError',
      _server_messages: JSON.stringify([
        JSON.stringify({ message: '<b>Row 1</b>: hours cannot be negative.' }),
      ]),
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status: 417 }))),
    )
    vi.stubGlobal('window', { csrf_token: 'tok', location: { replace: vi.fn(), reload: vi.fn() } })
    const error = await submitLog(storedLog({ docstatus: 0 })).catch((e: unknown) => e)
    vi.unstubAllGlobals()
    expect(error).toBeInstanceOf(ApiError)
    expect(errorText(error)).toBe('Row 1: hours cannot be negative.')
  })

  it('says the server could not be reached when there is no answer', () => {
    expect(errorText(new TypeError('Failed to fetch'))).toBe(
      'The server could not be reached. Check the connection and try again.',
    )
  })

  it('falls back to the HTTP status when the server sent no message', () => {
    expect(errorText(new ApiError('HTTP 502', 502))).toBe('HTTP 502')
  })
})
