import { describe, expect, it } from 'vitest'
import { serverMessage } from './api'

describe('serverMessage', () => {
  it("reads Frappe's _server_messages and strips HTML", () => {
    const body = {
      _server_messages: JSON.stringify([JSON.stringify({ message: '<b>Not permitted</b>' })]),
    }
    expect(serverMessage(body)).toBe('Not permitted')
  })

  it('returns an empty string for anything else', () => {
    expect(serverMessage(null)).toBe('')
    expect(serverMessage({ _server_messages: 'not json' })).toBe('')
  })
})
