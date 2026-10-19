// As hrms/frontend/src/data/session.js: the signed-in user comes from Frappe's `user_id` cookie.
export function sessionUser(): string | null {
  if (typeof document === 'undefined') return null
  const cookies = new URLSearchParams(document.cookie.split('; ').join('&'))
  const user = cookies.get('user_id')
  return user && user !== 'Guest' ? user : null
}
