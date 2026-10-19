<script setup lang="ts">
import { ref } from 'vue'
import { Button } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import InstallHint from '../components/InstallHint.vue'
import { getSessionContext, logout, type SessionContext } from '../data/session'

const ctx = ref<SessionContext | null>(null)
getSessionContext()
  .then((c) => (ctx.value = c))
  .catch(() => null) // the router already sent a failed lookup to the retry screen
</script>

<template>
  <TopBar :title="__('Profile', [], 'Card Mobile')" />
  <div class="space-y-5 p-4">
    <dl v-if="ctx" class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-1">
      <div class="p-4">
        <dt class="text-sm text-ink-gray-5">{{ __('Employee', [], 'Card Mobile') }}</dt>
        <dd class="font-medium" data-testid="employee">{{ ctx.employee?.employee_name }}</dd>
      </div>
      <div class="p-4">
        <dt class="text-sm text-ink-gray-5">{{ __('Company', [], 'Card Mobile') }}</dt>
        <dd>{{ ctx.employee?.company }}</dd>
      </div>
      <div class="p-4">
        <dt class="text-sm text-ink-gray-5">{{ __('User', [], 'Card Mobile') }}</dt>
        <dd class="break-all">{{ ctx.user }}</dd>
      </div>
    </dl>

    <InstallHint />

    <Button
      class="h-12 w-full"
      size="lg"
      icon-left="lucide-log-out"
      :label="__('Logout', [], 'Card Mobile')"
      @click="logout"
    />
    <p v-if="ctx" class="text-center text-xs text-ink-gray-4">Card {{ ctx.card_version }}</p>
  </div>
</template>
