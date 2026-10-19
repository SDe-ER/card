<script setup lang="ts">
import { Button } from 'frappe-ui'
</script>

<template>
  <div class="flex min-h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
    <span class="lucide-map-pin-off size-8 text-ink-gray-5" aria-hidden="true" />
    <p class="text-base text-ink-gray-7">{{ __('Page Not Found', [], 'Card Mobile') }}</p>
    <Button size="lg" icon-left="lucide-house" :label="__('Home', [], 'Card Mobile')" route="/" />
  </div>
</template>
