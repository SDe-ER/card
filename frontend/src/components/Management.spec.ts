import { describe, expect, it } from 'vitest'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from 'vue/server-renderer'

import ManagementLinks from './ManagementLinks.vue'
import homeSource from '../pages/Home.vue?raw'
import routerSource from '../router.ts?raw'
import { __ } from '../i18n'
import { isReviewer, REVIEW_ROLES } from '../data/management'

const RouterLink = defineComponent({
  props: ['to'],
  setup:
    (_, { slots, attrs }) =>
    () =>
      h('a', attrs, slots.default?.()),
})

describe('management view gating (issue #358)', () => {
  it('only review roles are reviewers', () => {
    expect(REVIEW_ROLES).toEqual(['Card Supervisor', 'Card Manager', 'System Manager'])
    expect(isReviewer(['Card Operator'])).toBe(false)
    expect(isReviewer(['Card User'])).toBe(false)
    expect(isReviewer([])).toBe(false)
    expect(isReviewer(undefined)).toBe(false)
    expect(isReviewer(['Card Operator', 'Card Supervisor'])).toBe(true)
    expect(isReviewer(['System Manager'])).toBe(true)
  })

  it('every management route is marked reviewer-only and the guard checks it', () => {
    for (const name of ['ManagementFleet', 'ManagementProjects', 'ManagementCards']) {
      const block = routerSource.slice(routerSource.indexOf(`name: '${name}'`)).split('},')[0]
      expect(block).toContain('reviewer: true')
    }
    expect(routerSource).toContain('to.meta.reviewer && !isReviewer(ctx.roles)')
  })

  it('the home draws the entry points for reviewers only', () => {
    expect(homeSource).toMatch(/<ManagementLinks[^>]*v-if="home\?\.reviewer"/)
  })

  it('the entry points name fleet, projects and monthly cards', async () => {
    const app = createSSRApp({ render: () => h(ManagementLinks) })
    app.config.globalProperties.__ = __
    app.component('RouterLink', RouterLink)
    const html = await renderToString(app)
    for (const label of ['Fleet', 'Projects', 'Monthly cards']) expect(html).toContain(label)
  })
})
