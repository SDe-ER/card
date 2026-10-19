<script setup lang="ts">
import { Button } from 'frappe-ui'
import { installPrompt } from '../install'

// Android/Chrome offers the prompt caught at start-up (main.ts); iPhone Safari has none, so it gets a hint.
const standalone =
  window.matchMedia('(display-mode: standalone)').matches ||
  (navigator as Navigator & { standalone?: boolean }).standalone === true
const ios = /iphone|ipad|ipod/i.test(navigator.userAgent)

async function install() {
  await installPrompt.value?.prompt()
  installPrompt.value = null
}
</script>

<template>
  <section
    v-if="!standalone && (installPrompt || ios)"
    class="space-y-3 rounded-lg border border-outline-gray-1 p-4"
  >
    <p class="font-medium">{{ __('Install the app') }}</p>
    <Button
      v-if="installPrompt"
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
