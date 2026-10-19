import { createRouter, createWebHistory } from 'vue-router'
import { getSessionContext, sessionUser } from './data/session'

export const router = createRouter({
  // the same path as `frontendRoute` in vite.config.ts
  history: createWebHistory('/cdms'),
  routes: [
    { path: '/', name: 'Home', component: () => import('./pages/Home.vue') },
    { path: '/new', name: 'NewRequest', component: () => import('./pages/NewRequest.vue') },
    { path: '/requests', name: 'Requests', component: () => import('./pages/Requests.vue') },
    { path: '/profile', name: 'Profile', component: () => import('./pages/Profile.vue') },
    { path: '/login', name: 'Login', component: () => import('./pages/Login.vue') },
    { path: '/no-access', name: 'NoAccess', component: () => import('./pages/NoAccess.vue') },
    { path: '/:path(.*)*', name: 'NotFound', component: () => import('./pages/NotFound.vue') },
  ],
})

// As hrms/frontend/src/main.js: guests go to the login view; a signed-in user needs a CARD role
// and an Active Employee linked to the account. The server checks every call regardless.
router.beforeEach(async (to) => {
  if (!sessionUser()) return to.name === 'Login' ? true : { name: 'Login' }
  if (to.name === 'NoAccess') return true
  const ctx = await getSessionContext()
  // an expired session: Frappe answers as Guest and resets the user_id cookie
  if (!ctx && !sessionUser()) return { name: 'Login' }
  if (!ctx || !ctx.employee) return { name: 'NoAccess' }
  if (to.name === 'Login') return { name: 'Home' }
  return true
})
