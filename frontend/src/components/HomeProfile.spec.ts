import { describe, expect, it } from 'vitest'
import { createSSRApp, h, type Component } from 'vue'
import { renderToString } from 'vue/server-renderer'

import HomeKpis from './HomeKpis.vue'
import ProfileDetails from './ProfileDetails.vue'
import homeSource from '../pages/Home.vue?raw'
import profileSource from '../pages/Profile.vue?raw'
import { __ } from '../i18n'
import { formatMoney, type HomeContext, type Profile } from '../data/home'

// Issue #357: the role-based home and the profile, rendered server-side with no browser. The
// server decides what a role receives; these tests pin that the screen draws only what it got.

async function render(component: Component, props: Record<string, unknown>) {
  const app = createSSRApp({ render: () => h(component, props) })
  app.config.globalProperties.__ = __
  return renderToString(app)
}

const kpis = {
  equipment: { active: 12, stopped: 2, maintenance: 1 },
  fleet_by_project: [
    { project: 'North Road', count: 7 },
    { project: null, count: 3 },
  ],
  requests_to_review: 4,
  logs_to_review: 9,
  alerts: { documents_expiring: 3 },
}

function home(overrides: Partial<HomeContext> = {}): HomeContext {
  return { reviewer: true, manager: false, kpis, financial: null, ...overrides }
}

describe('HomeKpis: role-based content', () => {
  it('an operator (no kpis) sees no KPI block at all', async () => {
    const html = await render(HomeKpis, {
      home: home({ reviewer: false, kpis: null }),
    })
    expect(html).not.toContain('data-testid')
    expect(html).not.toMatch(/Revenue|Cost|This month/)
  })

  it('a supervisor sees operational KPIs and no money', async () => {
    const html = await render(HomeKpis, { home: home() })
    expect(html).toContain('data-testid="fleet"')
    expect(html).toContain('data-testid="requests-to-review"')
    expect(html).toContain('data-testid="alerts"')
    expect(html).toContain('No project')
    expect(html).not.toContain('data-testid="financial"')
    expect(html).not.toMatch(/Revenue|Cost|SAR/)
  })

  it('hides the alert when nothing is expiring', async () => {
    const html = await render(HomeKpis, {
      home: home({ kpis: { ...kpis, alerts: { documents_expiring: 0 } } }),
    })
    expect(html).not.toContain('data-testid="alerts"')
  })

  it('a manager sees full-precision financial figures from the server', async () => {
    const html = await render(HomeKpis, {
      home: home({
        manager: true,
        financial: {
          month: 11,
          year: 2026,
          by_company: [{ company: 'Example Co', currency: 'SAR', revenue: 128450, cost: 90210.5 }],
        },
      }),
    })
    expect(html).toContain('128,450.00 SAR')
    expect(html).toContain('90,210.50 SAR')
  })

  it('says so when a manager has no submitted cards this month', async () => {
    const html = await render(HomeKpis, {
      home: home({ manager: true, financial: { month: 11, year: 2026, by_company: [] } }),
    })
    expect(html).toContain('No submitted cards this month.')
  })
})

describe('formatMoney', () => {
  it('never abbreviates', () => {
    expect(formatMoney(1234567.5, 'SAR')).toBe('1,234,567.50 SAR')
    expect(formatMoney(5, null)).toBe('5.00')
  })
})

const profile: Profile = {
  user: 'ali@example.com',
  full_name: 'Ali Example',
  email: 'ali@example.com',
  phone: '0500000000',
  image: null,
  employee: { name: 'HR-EMP-00001', designation: 'Operator', branch: null },
  company: 'Example Co',
  currency: 'SAR',
  number_format: '#,###.##',
  language: 'en',
  roles: ['Card Operator'],
  card_version: '4.14.3',
}

describe('ProfileDetails', () => {
  it('shows live employee data and only the roles held', async () => {
    const html = await render(ProfileDetails, { profile, online: true })
    for (const text of [
      'Ali Example',
      'HR-EMP-00001',
      'Operator',
      'Example Co',
      '0500000000',
      'SAR',
    ]) {
      expect(html).toContain(text)
    }
    expect(html).toContain('data-role="Card Operator"')
    expect(html).not.toContain('data-role="Card Manager"')
    expect(html).toContain('Enter daily logs and request needs for your machines')
  })

  it('leaves out a field the user has no value for', async () => {
    const html = await render(ProfileDetails, { profile, online: true })
    expect(html).not.toContain('data-testid="branch"')
  })

  it('says when the phone is offline', async () => {
    const html = await render(ProfileDetails, { profile, online: false })
    expect(html).toContain('Offline')
  })
})

describe('pages', () => {
  it('the home asks the server for the role context and draws it with HomeKpis', () => {
    expect(homeSource).toContain('getHomeContext')
    expect(homeSource).toContain('<HomeKpis')
    // no role logic of its own for money: the server sends it or not
    expect(homeSource).not.toMatch(/Card Manager|System Manager/)
  })

  it('the profile switches language through the server and reloads', () => {
    expect(profileSource).toContain('setLanguage')
    expect(profileSource).toContain('window.location.reload()')
    expect(profileSource).toContain('data-testid="language-toggle"')
  })
})
