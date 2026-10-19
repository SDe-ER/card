<script setup lang="ts">
import { Button } from 'frappe-ui'
import { logout } from '../data/session'
// served by Frappe (not bundled), the same file as the Desk logo
const CARD_LOGO = '/assets/card/images/card-logo.svg'
</script>

<template>
  <div
    class="flex min-h-dvh flex-col items-center justify-center gap-6 p-6 text-center"
    data-testid="no-access"
  >
    <img :src="CARD_LOGO" alt="" class="size-14" />
    <p class="text-base text-ink-gray-7">
      {{ __('Your account is not set up to ask for equipment needs. Ask your supervisor.') }}
    </p>
    <Button size="lg" :label="__('Logout', [], 'Card Mobile')" @click="logout" />
  </div>
</template>
