import { get, post } from './api'

// As hrms/frontend/src/data/session.js: the signed-in user comes from Frappe's `user_id` cookie.
export function sessionUser(): string | null {
  const cookies = new URLSearchParams(document.cookie.split('; ').join('&'))
  const user = cookies.get('user_id')
  return user && user !== 'Guest' ? user : null
}

export interface SessionContext {
  user: string
  full_name: string
  roles: string[]
  employee: { name: string; employee_name: string; company: string } | null
  card_version: string
}

let context: Promise<SessionContext | null> | null = null

export function getSessionContext(): Promise<SessionContext | null> {
  if (!context) {
    context = get<SessionContext>('card.mobile.get_session_context').catch(() => null)
  }
  return context
}

export async function login(usr: string, pwd: string) {
  const message = await post<string>('login', { usr, pwd })
  // Frappe answers "Logged In" to System Users and "No App" to Website Users; both are signed in.
  // A full load gives the page the new session's CSRF token.
  if (message === 'Logged In' || message === 'No App') window.location.replace('/cdms/')
  return message
}

export async function logout() {
  await post('logout')
  window.location.replace('/cdms/login')
}
