import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { TabButtons } from 'frappe-ui'
import page from './NewRequest.vue?raw'

const kinds = [
  { label: 'Part or consumable', value: 'Part' },
  { label: 'Tool', value: 'Tool' },
]

const render = (props: Record<string, unknown>) =>
  renderToString(createSSRApp({ render: () => h(TabButtons, { modelValue: 'Part', ...props }) }))

// frappe-ui 1.0.2 TabButtons reads `options`; with `buttons` it renders no choice at all, so an
// operator could not ask for a tool (every line went out as a part).
describe('request line kind selector', () => {
  it('shows both kinds through the options prop', async () => {
    const html = await render({ options: kinds })
    expect(html).toContain('Part or consumable')
    expect(html).toContain('Tool')
  })

  it('renders no choice with the old buttons prop', async () => {
    const html = await render({ buttons: kinds })
    expect(html).not.toContain('Tool')
  })

  it('NewRequest passes the kinds as options', () => {
    expect(page).toMatch(/<TabButtons v-model="line\.kind" :options="kinds" \/>/)
  })
})
