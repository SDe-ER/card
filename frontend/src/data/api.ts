// Calls to Frappe whitelisted methods. GET for reads (CARD read endpoints accept GET only),
// POST with the session's CSRF token for writes.

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

async function handle<T>(res: Response): Promise<T> {
  const body = (await res.json().catch(() => null)) as Record<string, unknown> | null
  if (!res.ok) {
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
  return handle<T>(res)
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
  return handle<T>(res)
}
