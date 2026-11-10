// Calls to Frappe whitelisted methods. GET for reads (CARD read endpoints accept GET only),
// POST with the session's CSRF token for writes.
import { sessionUser } from './cookie'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// Frappe returns user-facing messages in `_server_messages` (a JSON list of JSON objects).
export function serverMessage(body: Record<string, unknown> | null): string {
  try {
    const list = JSON.parse(String(body?._server_messages ?? '[]')) as string[]
    let text = list.map((m) => JSON.parse(m).message as string).join('\n')
    // shown as plain text (Vue escapes it); drop Frappe's markup, repeated until nothing is left
    let previous
    do {
      previous = text
      text = text.replace(/<[^>]*>/g, '')
    } while (text !== previous)
    return text
  } catch {
    return ''
  }
}

// A session that ended while the app was open: Frappe answers 401/403 and resets the `user_id`
// cookie, so the user goes back to sign-in. A stale CSRF token needs a fresh page load. The sign-in
// call itself answers 401 for a wrong password, which stays an error on the form.
export function sessionAction(
  method: string,
  status: number,
  excType: unknown,
  signedIn: boolean,
): 'login' | 'reload' | null {
  if (method === 'login') return null
  if (excType === 'CSRFTokenError') return 'reload'
  if ((status === 401 || status === 403) && !signedIn) return 'login'
  return null
}

async function handle<T>(method: string, res: Response): Promise<T> {
  const body = (await res.json().catch(() => null)) as Record<string, unknown> | null
  if (!res.ok) {
    const action = sessionAction(method, res.status, body?.exc_type, !!sessionUser())
    if (action === 'login') window.location.replace('/cdms/login')
    if (action === 'reload') window.location.reload()
    // e.g. a failed login answers {message: "Invalid login credentials"} without _server_messages
    const message = serverMessage(body) || (typeof body?.message === 'string' ? body.message : '')
    throw new ApiError(message || `HTTP ${res.status}`, res.status)
  }
  return body?.message as T
}

export async function get<T>(method: string, params: Record<string, string> = {}): Promise<T> {
  const query = new URLSearchParams(params).toString()
  const res = await fetch(`/api/method/${method}${query ? `?${query}` : ''}`, {
    headers: { Accept: 'application/json' },
  })
  return handle<T>(method, res)
}

export async function post<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch(`/api/method/${method}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Frappe-CSRF-Token': window.csrf_token || '',
    },
    body: JSON.stringify(params),
  })
  return handle<T>(method, res)
}

// Frappe's standard REST resource routes (/api/resource/<doctype>), under the user's own
// permissions: the server applies the DocType's role permissions, `if_owner`, the company scope
// and every controller rule. Errors come back as `_server_messages`, as for /api/method.
function resourceUrl(doctype: string, name?: string) {
  const base = `/api/resource/${encodeURIComponent(doctype)}`
  return name ? `${base}/${encodeURIComponent(name)}` : base
}

function writeHeaders() {
  return {
    Accept: 'application/json',
    'Content-Type': 'application/json',
    'X-Frappe-CSRF-Token': window.csrf_token || '',
  }
}

// the body of a resource route is {data: ...}; `handle` reads `message`, so wrap it
async function handleResource<T>(res: Response): Promise<T> {
  const body = (await res
    .clone()
    .json()
    .catch(() => null)) as Record<string, unknown> | null
  if (!res.ok) return handle<T>('resource', res)
  return body?.data as T
}

export async function listResource<T>(
  doctype: string,
  params: { fields: string[]; filters?: unknown[]; order_by?: string; limit?: number },
): Promise<T[]> {
  const query = new URLSearchParams({
    fields: JSON.stringify(params.fields),
    limit_page_length: String(params.limit ?? 20),
  })
  if (params.filters) query.set('filters', JSON.stringify(params.filters))
  if (params.order_by) query.set('order_by', params.order_by)
  const res = await fetch(`${resourceUrl(doctype)}?${query}`, {
    headers: { Accept: 'application/json' },
  })
  return handleResource<T[]>(res)
}

export async function getResource<T>(doctype: string, name: string): Promise<T> {
  const res = await fetch(resourceUrl(doctype, name), { headers: { Accept: 'application/json' } })
  return handleResource<T>(res)
}

export async function insertResource<T>(
  doctype: string,
  data: Record<string, unknown>,
): Promise<T> {
  const res = await fetch(resourceUrl(doctype), {
    method: 'POST',
    headers: writeHeaders(),
    body: JSON.stringify(data),
  })
  return handleResource<T>(res)
}

export async function updateResource<T>(
  doctype: string,
  name: string,
  data: Record<string, unknown>,
): Promise<T> {
  const res = await fetch(resourceUrl(doctype, name), {
    method: 'PUT',
    headers: writeHeaders(),
    body: JSON.stringify(data),
  })
  return handleResource<T>(res)
}
