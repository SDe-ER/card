<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { ErrorMessage, LoadingIndicator } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { getPortal, type PortalContext } from '../data/needs'

const route = useRoute()
const portal = ref<PortalContext | null>(null)
const error = ref('')

getPortal()
  .then((p) => (portal.value = p))
  .catch((e: Error) => (error.value = e.message))
</script>

<template>
  <TopBar :title="__('My requests')" />
  <div class="space-y-3 p-4">
    <p
      v-if="route.query.sent"
      class="rounded-lg bg-surface-green-1 p-3 text-ink-green-3"
      role="status"
    >
      {{ __('Your request was sent to the supervisor.') }}
    </p>
    <LoadingIndicator v-if="!portal && !error" class="mx-auto size-6" />
    <ErrorMessage :message="error" />
    <p
      v-if="portal && !portal.requests.length"
      class="rounded-lg bg-surface-gray-1 p-4 text-ink-gray-6"
    >
      {{ __('No requests yet.') }}
    </p>
    <article
      v-for="r in portal?.requests ?? []"
      :key="r.name"
      class="space-y-2 rounded-lg border border-outline-gray-1 p-4"
      data-testid="request"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <p class="truncate font-medium">{{ r.equipment_name }}</p>
          <p class="text-xs text-ink-gray-5">{{ r.name }} · {{ r.request_date }}</p>
        </div>
        <StatusBadge :status="r.review_status" />
      </div>
      <ul class="space-y-1 text-sm text-ink-gray-7">
        <li v-for="(line, i) in r.items" :key="i" class="flex justify-between gap-3">
          <span class="min-w-0 truncate">{{ line.description || line.item_code }}</span>
          <span class="shrink-0 tabular-nums">{{ line.qty }}</span>
        </li>
      </ul>
    </article>
  </div>
</template>
