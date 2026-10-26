import { createRouter, createWebHistory } from 'vue-router'
import { getSessionContext, sessionUser } from './data/session'

export const router = createRouter({
  // the same path as `frontendRoute` in vite.config.ts
  history: createWebHistory('/cdms'),
  routes: [
    { path: '/', name: 'Home', component: () => import('./pages/Home.vue') },
    { path: '/new', name: 'NewRequest', component: () => import('./pages/NewRequest.vue') },
    { path: '/requests', name: 'Requests', component: () => import('./pages/Requests.vue') },
    { path: '/catalog', name: 'Catalog', component: () => import('./pages/Catalog.vue') },
    { path: '/profile', name: 'Profile', component: () => import('./pages/Profile.vue') },
    { path: '/login', name: 'Login', component: () => import('./pages/Login.vue') },
    { path: '/no-access', name: 'NoAccess', component: () => import('./pages/NoAccess.vue') },
    { path: '/:path(.*)*', name: 'NotFound', component: () => import('./pages/NotFound.vue') },
  ],
})

// As hrms/frontend/src/main.js: guests go to the login view; a signed-in user needs a CARD role
// and an Active Employee linked to the account. A catalog viewer (Card User) opens only the
// catalog and his profile. The server checks every call regardless.
export const CATALOG_ONLY_PAGES = ['Catalog', 'Profile']

router.beforeEach(async (to) => {
  if (!sessionUser()) return to.name === 'Login' ? true : { name: 'Login' }
  if (to.name === 'NoAccess') return true
  let ctx
  try {
    ctx = await getSessionContext()
  } catch {
    // no answer from the server (offline, server error): say so and offer a retry
    return { name: 'NoAccess', query: { offline: '1' } }
  }
  // an expired session: Frappe answers as Guest and resets the user_id cookie
  if (!ctx && !sessionUser()) return { name: 'Login' }
  if (ctx?.catalog_only) return CATALOG_ONLY_PAGES.includes(String(to.name)) || { name: 'Catalog' }
  if (!ctx || !ctx.employee) return { name: 'NoAccess' }
  if (to.name === 'Login') return { name: 'Home' }
  return true
})
