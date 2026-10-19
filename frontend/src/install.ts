import { ref } from 'vue'

// Android/Chrome fires `beforeinstallprompt` once, early in the page load, whatever screen is open,
// so it is caught here at start-up (as Frappe HR's App-level InstallPrompt) and offered on Profile.
export interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>
}

export const installPrompt = ref<InstallPromptEvent | null>(null)

export function listenForInstallPrompt() {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    installPrompt.value = e as InstallPromptEvent
  })
  window.addEventListener('appinstalled', () => (installPrompt.value = null))
}
