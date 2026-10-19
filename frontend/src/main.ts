import { createApp } from 'vue'
import App from './App.vue'
import { __ } from './i18n'
import { listenForInstallPrompt } from './install'
import { router } from './router'
import './style.css'

// Language and direction come from the boot data before the first render.
document.documentElement.lang = window.lang || 'en'
document.documentElement.dir = window.dir || 'ltr'

listenForInstallPrompt()

const app = createApp(App)
app.config.globalProperties.__ = __
app.use(router)
router.isReady().then(() => app.mount('#app'))

if ('serviceWorker' in navigator) {
  // A new build's worker takes over at once (skipWaiting + clientsClaim); reload once so the page
  // and its lazy chunks come from the same build.
  const hadController = !!navigator.serviceWorker.controller
  let reloading = false
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (hadController && !reloading) {
      reloading = true
      window.location.reload()
    }
  })
  navigator.serviceWorker.register('/cdms/sw.js', { scope: '/cdms/' })
}
