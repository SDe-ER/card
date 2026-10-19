import { afterEach, describe, expect, it, vi } from 'vitest'

function reply(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

describe('getSessionContext', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('does not keep a failed request, so the next navigation asks again', async () => {
    const fetch = vi
      .fn()
      .mockImplementationOnce(() => Promise.reject(new TypeError('Failed to fetch')))
      .mockImplementationOnce(() => reply(200, { message: { user: 'op@example.com' } }))
    vi.stubGlobal('fetch', fetch)
    const { getSessionContext } = await import('./session')
    await expect(getSessionContext()).rejects.toThrow('Failed to fetch')
    await expect(getSessionContext()).resolves.toEqual({ user: 'op@example.com' })
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('keeps a refusal as "no access"', async () => {
    vi.stubGlobal('window', { location: { replace: vi.fn(), reload: vi.fn() } })
    const fetch = vi.fn(() => reply(403, { exc_type: 'PermissionError' }))
    vi.stubGlobal('fetch', fetch)
    const { getSessionContext } = await import('./session')
    await expect(getSessionContext()).resolves.toBeNull()
    await expect(getSessionContext()).resolves.toBeNull()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
