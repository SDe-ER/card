import { describe, expect, it } from 'vitest'
import { translate } from './i18n'

describe('translate', () => {
  it('returns the translation when there is one', () => {
    expect(translate({ 'My requests': 'طلباتي' }, 'My requests')).toBe('طلباتي')
  })

  it('falls back to the English source', () => {
    expect(translate(undefined, 'My requests')).toBe('My requests')
    expect(translate({}, 'My requests')).toBe('My requests')
  })

  it('fills numbered placeholders and keeps missing ones', () => {
    expect(translate({}, '{0} of {1}', [2, 5])).toBe('2 of 5')
    expect(translate({}, '{0} of {1}', [2])).toBe('2 of {1}')
  })

  it('never translates the app name Card', () => {
    expect(translate({}, 'Card')).toBe('Card')
  })
})
