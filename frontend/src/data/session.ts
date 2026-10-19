import { ApiError, get, post } from './api'

export { sessionUser } from './cookie'

export interface SessionContext {
  user: string
  full_name: string
  roles: string[]
  employee: { name: string; employee_name: string; company: string } | null
  card_version: string
}

let context: Promise<SessionContext | null> | null = null

// A refusal (no CARD role, or a session that ended) is an answer and is kept for the page's life.
// A failed request (no network, server error) is not: it rejects and the next navigation asks again.
export function getSessionContext(): Promise<SessionContext | null> {
  if (!context) {
    context = get<SessionContext>('card.mobile.get_session_context').catch((e: unknown) => {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null
      context = null
      throw e
    })
  }
  return context
}

export async function login(usr: string, pwd: string) {
  const message = await post<string>('login', { usr, pwd })
  // Frappe answers "Logged In" to System Users and "No App" to Website Users; both are signed in.
  // A full load gives the page the new session's CSRF token.
  if (message === 'Logged In' || message === 'No App') window.location.replace('/cdms/')
  // Anything else needs a step this screen does not have (e.g. two-factor verification):
  // Frappe's own login page handles it and comes back here.
  else window.location.assign('/login?redirect-to=/cdms/')
  return message
}

export async function logout() {
  // the session may already be gone on the server; leave the app either way
  await post('logout').catch(() => null)
  window.location.replace('/cdms/login')
}
