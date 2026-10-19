import { describe, expect, it } from 'vitest'
import { serverMessage, sessionAction } from './api'

describe('serverMessage', () => {
  it("reads Frappe's _server_messages and strips HTML", () => {
    const body = {
      _server_messages: JSON.stringify([JSON.stringify({ message: '<b>Not permitted</b>' })]),
    }
    expect(serverMessage(body)).toBe('Not permitted')
  })

  it('leaves no tag behind when tags are nested', () => {
    const body = {
      _server_messages: JSON.stringify([JSON.stringify({ message: '<scr<b>ipt>x' })]),
    }
    expect(serverMessage(body)).toBe('ipt>x')
  })

  it('returns an empty string for anything else', () => {
    expect(serverMessage(null)).toBe('')
    expect(serverMessage({ _server_messages: 'not json' })).toBe('')
  })
})

describe('sessionAction', () => {
  it('sends an ended session back to sign-in', () => {
    expect(sessionAction('card.materials.get_portal_context', 403, 'PermissionError', false)).toBe(
      'login',
    )
    expect(sessionAction('logout', 401, undefined, false)).toBe('login')
  })

  it('keeps a refusal for a signed-in user on the screen', () => {
    expect(sessionAction('card.materials.submit_needs', 403, 'PermissionError', true)).toBeNull()
  })

  it('never redirects the sign-in call itself (wrong password)', () => {
    expect(sessionAction('login', 401, 'AuthenticationError', false)).toBeNull()
  })

  it('reloads for a stale CSRF token', () => {
    expect(sessionAction('card.materials.submit_needs', 400, 'CSRFTokenError', true)).toBe(
      'reload',
    )
  })
})
