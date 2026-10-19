// Same worker as hrms/frontend/public/sw.js, without push: precache the build, drop old caches,
// take over at once. No runtime or API caching (no offline data or writes).
import { cleanupOutdatedCaches, precacheAndRoute } from 'workbox-precaching'
import { clientsClaim } from 'workbox-core'

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

self.skipWaiting()
clientsClaim()
