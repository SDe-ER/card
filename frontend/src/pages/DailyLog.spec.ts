import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, type Component } from 'vue'
import { renderToString } from 'vue/server-renderer'

// FR-150: the daily log components rendered (server-side, no browser needed) with frappe-ui
// replaced by plain stand-ins, so the tests read what the operator sees and which actions exist.
vi.mock('frappe-ui', () => {
  const Button = defineComponent({
    props: ['label', 'route', 'loading', 'disabled', 'icon', 'iconLeft', 'variant'],
    setup(props, { attrs }) {
      return () =>
        h(
          'button',
          { ...attrs, 'data-route': props.route ? JSON.stringify(props.route) : undefined },
          props.label,
        )
    },
  })
  const Badge = defineComponent({
    props: ['label', 'theme', 'size'],
    setup:
      (props, { attrs }) =>
      () =>
        h('span', { ...attrs, 'data-theme': props.theme }, props.label),
  })
  const ErrorMessage = defineComponent({
    props: ['message'],
    setup:
      (props, { attrs }) =>
      () =>
        props.message ? h('div', { ...attrs, role: 'alert' }, props.message) : null,
  })
  const FormControl = defineComponent({
    props: ['label', 'type', 'options', 'modelValue'],
    setup:
      (props, { attrs }) =>
      () =>
        h('label', { ...attrs, 'data-type': props.type }, [
          props.label,
          props.type === 'select'
            ? h(
                'select',
                (props.options ?? []).map((o: { label: string; value: string }) =>
                  h('option', { value: o.value }, o.label),
                ),
              )
            : h('input', { value: props.modelValue ?? '' }),
        ]),
  })
  return { Badge, Button, ErrorMessage, FormControl }
})

import DailyLogBadge from '../components/DailyLogBadge.vue'
import DailyLogDetail from '../components/DailyLogDetail.vue'
import DailyLogRowFields from '../components/DailyLogRowFields.vue'
import detailSource from '../components/DailyLogDetail.vue?raw'
import rowSource from '../components/DailyLogRowFields.vue?raw'
import badgeSource from '../components/DailyLogBadge.vue?raw'
import listSource from './DailyLogList.vue?raw'
import formSource from './DailyLogForm.vue?raw'
import viewSource from './DailyLogView.vue?raw'
import { __ } from '../i18n'
import type { DailyLog } from '../data/dailyLog'

const RouterLink = defineComponent({
  props: ['to'],
  setup:
    (_, { slots, attrs }) =>
    () =>
      h('a', attrs, slots.default?.()),
})

async function render(component: Component, props: Record<string, unknown>, dir = 'rtl') {
  const app = createSSRApp({ render: () => h('div', { dir }, [h(component, props)]) })
  app.config.globalProperties.__ = __
  app.component('RouterLink', RouterLink)
  return renderToString(app)
}

function log(overrides: Partial<DailyLog> = {}): DailyLog {
  return {
    name: 'CDL-00007',
    company: 'Test Company',
    project: 'PROJ-A',
    log_date: '2026-11-09',
    notes: '',
    docstatus: 1,
    approval_status: 'Pending',
    return_reason: null,
    modified: '2026-11-09 10:00:00',
    rows: [
      {
        name: 'r1',
        equipment: 'CEQ-0001',
        equipment_name: 'Loader 1',
        day_hours: 9.5,
        night_hours: 0,
        stopped_hours: 1,
        stop_reason: null,
      },
    ],
    ...overrides,
  }
}

function actionsIn(html: string): string[] {
  return [...html.matchAll(/data-action="([a-z]+)"/g)].map((m) => m[1])
}

const APPROVAL_LABEL = /approve|verify|return daily log|reject/i
const MONEY = /rate|amount|price|cost|currency|SAR|billing/i

describe('DailyLogDetail: actions per state and role', () => {
  const cases: [string, Partial<DailyLog>, string[], string[]][] = [
    ['operator, draft', { docstatus: 0 }, ['Card Operator'], ['submit', 'edit']],
    ['operator, pending', {}, ['Card Operator'], []],
    ['operator, verified', { approval_status: 'Verified by supervisor' }, ['Card Operator'], []],
    ['operator, approved', { approval_status: 'Approved' }, ['Card Operator'], []],
    [
      'operator, returned',
      { approval_status: 'Returned for correction', return_reason: 'Day hours too high' },
      ['Card Operator'],
      ['correct'],
    ],
    ['supervisor, pending', {}, ['Card Supervisor'], ['desk']],
    [
      'manager, verified',
      { approval_status: 'Verified by supervisor' },
      ['Card Manager'],
      ['desk'],
    ],
  ]

  for (const [title, overrides, roles, expected] of cases) {
    it(`${title}: ${expected.join(', ') || 'no action'}`, async () => {
      const html = await render(DailyLogDetail, { log: log(overrides), roles })
      expect(actionsIn(html)).toEqual(expected)
      // no approve, verify or return button for anyone; the Desk link is a plain link
      const buttons = [...html.matchAll(/<button[^>]*>([^<]*)<\/button>/g)].map((m) => m[1])
      expect(buttons.filter((b) => APPROVAL_LABEL.test(b))).toEqual([])
    })
  }

  it('links a reviewer to the log in CARD Desk', async () => {
    const html = await render(DailyLogDetail, { log: log(), roles: ['Card Manager'] })
    expect(html).toContain('href="/app/card-daily-log/CDL-00007"')
  })
})

describe('DailyLogDetail: status and content', () => {
  it('shows the return reason of a returned log', async () => {
    const html = await render(DailyLogDetail, {
      log: log({
        approval_status: 'Returned for correction',
        return_reason: 'Day hours too high',
      }),
      roles: ['Card Operator'],
    })
    expect(html).toContain('data-state="Returned"')
    expect(html).toContain('Day hours too high')
  })

  it('shows the stored status, never one the client made up', async () => {
    const html = await render(DailyLogBadge, {
      log: { docstatus: 0, approval_status: 'Approved' },
    })
    expect(html).toContain('data-state="Draft"')
  })

  it('shows hours and no money', async () => {
    const html = await render(DailyLogDetail, { log: log(), roles: ['Card Operator'] })
    expect(html).toContain('9.5')
    expect(html.replace(/<[^>]*>/g, ' ')).not.toMatch(MONEY)
  })

  it('shows the error the server sent', async () => {
    const html = await render(DailyLogDetail, {
      log: log({ docstatus: 0 }),
      roles: ['Card Operator'],
      error: 'Equipment CEQ-0001 is not on project PROJ-A on 2026-11-09.',
    })
    expect(html).toMatch(
      /role="alert"[^>]*>Equipment CEQ-0001 is not on project PROJ-A on 2026-11-09\.</,
    )
  })

  it('shows no error box without an error', async () => {
    const html = await render(DailyLogDetail, { log: log(), roles: ['Card Operator'] })
    expect(html).not.toContain('role="alert"')
  })
})

describe('right-to-left (Arabic)', () => {
  const sources = {
    DailyLogDetail: detailSource,
    DailyLogRowFields: rowSource,
    DailyLogBadge: badgeSource,
    DailyLogList: listSource,
    DailyLogForm: formSource,
    DailyLogView: viewSource,
  }
  // physical sides do not flip in RTL; the logical ones (ms-, me-, ps-, pe-, start, end) do
  const PHYSICAL = /\b(?:m|p)[lr]-\d|\b(?:left|right)-\d|\btext-(?:left|right)\b|\brounded-[lr]\b/

  for (const [name, source] of Object.entries(sources)) {
    it(`${name} uses logical sides only`, () => {
      expect(source).not.toMatch(PHYSICAL)
    })
  }

  it('renders the detail in an RTL page: chevrons flip, numbers and dates stay LTR', async () => {
    const html = await render(DailyLogDetail, { log: log(), roles: ['Card Operator'] }, 'rtl')
    expect(html).toContain('<div dir="rtl">')
    expect(html).toMatch(/<bdi dir="ltr" class="tabular-nums">2026-11-09<\/bdi>/)
    expect(html).toMatch(/<bdi dir="ltr" class="tabular-nums">9\.5<\/bdi>/)
    expect(listSource).toMatch(/lucide-chevron-right[^"]*rtl:rotate-180/)
  })

  it('renders a row editor with its labels and an RTL-safe icon gap', async () => {
    const row = log().rows[0]
    const html = await render(DailyLogRowFields, {
      modelValue: row,
      label: 'Loader 1',
      index: 0,
      reasons: null,
      removable: true,
    })
    expect(html).toContain('Loader 1')
    expect(html).toContain('Day shift hours')
    expect(html).toContain('Stopped hours')
    expect(html).toMatch(/lucide-truck me-2/)
    // an operator cannot read the stop reasons: no picker
    expect(html).not.toContain('Stop reason')
  })

  it('offers the stop reasons to a user who may read them', async () => {
    const html = await render(DailyLogRowFields, {
      modelValue: log().rows[0],
      label: 'Loader 1',
      index: 0,
      reasons: [{ name: 'SR-1', reason_name: 'Breakdown' }],
      removable: false,
    })
    expect(html).toContain('Stop reason')
    expect(html).toContain('<option value="SR-1">Breakdown</option>')
  })
})

describe('translatable strings', () => {
  it('passes every visible string of the daily log screens through __()', () => {
    for (const source of [detailSource, rowSource, listSource, formSource, viewSource]) {
      const template = source.slice(source.indexOf('<template>'))
      // text between tags that is not an interpolation or whitespace
      const bare = [...template.matchAll(/>\s*([^<>{}\s][^<>{}]*?)\s*</g)]
        .map((m) => m[1].trim())
        .filter((t) => t && !/^[·:]$/.test(t))
      expect(bare).toEqual([])
      // literal labels and titles are translated too
      expect(template).not.toMatch(/\s(?:label|title|placeholder|message)="[A-Za-z]/)
    }
  })
})
