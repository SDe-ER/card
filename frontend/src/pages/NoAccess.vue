<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import { logout } from '../data/session'
// served by Frappe (not bundled), the same file as the Desk logo
const CARD_LOGO = '/assets/card/images/card-logo.svg'
// the router sends `offline` when the server gave no answer, which is not a missing permission
const offline = !!useRoute().query.offline

function retry() {
  window.location.replace('/cdms/')
}
</script>

<template>
  <div
    class="flex min-h-dvh flex-col items-center justify-center gap-6 p-6 text-center"
    data-testid="no-access"
  >
    <img :src="CARD_LOGO" alt="" class="size-14" />
    <template v-if="offline">
      <p class="text-base text-ink-gray-7">
        {{
          __(
            'The server could not be reached. Check the connection and try again.',
            [],
            'Card Mobile',
          )
        }}
      </p>
      <Button
        size="lg"
        variant="solid"
        :label="__('Try again', [], 'Card Mobile')"
        @click="retry"
      />
    </template>
    <template v-else>
      <p class="text-base text-ink-gray-7">
        {{ __('Your account is not set up to ask for equipment needs. Ask your supervisor.') }}
      </p>
      <Button size="lg" :label="__('Logout', [], 'Card Mobile')" @click="logout" />
    </template>
  </div>
</template>
