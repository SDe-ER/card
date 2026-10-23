import { describe, expect, it } from 'vitest'
import page from './NewRequest.vue?raw'

// frappe-ui 1.0.2 TabButtons reads `options`; with `buttons` the kind choice is not shown.
describe('NewRequest', () => {
  it('gives the line kinds to TabButtons as options', () => {
    expect(page).toMatch(/<TabButtons\b[^>]*\s:options="kinds"/)
    expect(page).not.toMatch(/<TabButtons\b[^>]*\s:buttons=/)
  })

  it('offers the two kinds the server stores', () => {
    expect(page).toMatch(/const kinds = \[[^\]]*value: 'Part'[^\]]*value: 'Tool'[^\]]*\]/)
  })
})
