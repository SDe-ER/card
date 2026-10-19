<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { Button } from 'frappe-ui'

// Android/Chrome offers `beforeinstallprompt`; iPhone Safari has no prompt, so it gets a hint.
interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>
}

const standalone =
  window.matchMedia('(display-mode: standalone)').matches ||
  (navigator as Navigator & { standalone?: boolean }).standalone === true
const ios = /iphone|ipad|ipod/i.test(navigator.userAgent)
const deferred = ref<InstallPromptEvent | null>(null)

function onPrompt(e: Event) {
  e.preventDefault()
  deferred.value = e as InstallPromptEvent
}
window.addEventListener('beforeinstallprompt', onPrompt)
onBeforeUnmount(() => window.removeEventListener('beforeinstallprompt', onPrompt))

async function install() {
  await deferred.value?.prompt()
  deferred.value = null
}
</script>

<template>
  <section
    v-if="!standalone && (deferred || ios)"
    class="space-y-3 rounded-lg border border-outline-gray-1 p-4"
  >
    <p class="font-medium">{{ __('Install the app') }}</p>
    <Button
      v-if="deferred"
      class="h-12 w-full"
      size="lg"
      icon-left="lucide-download"
      :label="__('Install the app')"
      @click="install"
    />
    <p v-else class="text-sm text-ink-gray-6">
      {{ __('On iPhone, tap Share, then Add to Home Screen.') }}
    </p>
  </section>
</template>
