<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, ErrorMessage, LoadingIndicator } from 'frappe-ui'
import { List, ListCell, ListRow, ListRows } from 'frappe-ui/list'
import TopBar from '../components/TopBar.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { getPortal, type PortalContext } from '../data/needs'
import { getSessionContext, type SessionContext } from '../data/session'

const ctx = ref<SessionContext | null>(null)
const portal = ref<PortalContext | null>(null)
const error = ref('')

getSessionContext()
  .then((c) => (ctx.value = c))
  .catch(() => null) // the router already sent a failed lookup to the retry screen
getPortal(true)
  .then((p) => (portal.value = p))
  .catch((e: Error) => (error.value = e.message))

const pending = computed(
  () =>
    portal.value?.requests.filter((r) => !['Approved', 'Rejected'].includes(r.review_status)) ??
    [],
)
// Supervisors and managers review and approve in CARD Desk (CARD Mobile screens come later).
const reviewer = computed(() => ctx.value?.roles.some((r) => r !== 'Card Operator') ?? false)
</script>

<template>
  <TopBar title="Card" />
  <div class="space-y-5 p-4">
    <p class="text-lg font-medium" data-testid="employee">{{ ctx?.employee?.employee_name }}</p>

    <LoadingIndicator v-if="!portal && !error" class="mx-auto size-6" />
    <ErrorMessage :message="error" />

    <template v-if="portal">
      <Button
        v-if="portal.machines.length"
        class="h-12 w-full"
        size="lg"
        variant="solid"
        icon-left="lucide-circle-plus"
        :label="__('New request')"
        :route="{ name: 'NewRequest' }"
      />

      <section class="space-y-2">
        <h2 class="text-sm font-medium text-ink-gray-5">
          {{ __('Equipment', [], 'Card Mobile') }}
        </h2>
        <p v-if="!portal.machines.length" class="rounded-lg bg-surface-gray-1 p-4 text-ink-gray-6">
          {{ __('No equipment is assigned to you this month.') }}
        </p>
        <List
          v-else
          :columns="['auto', 'minmax(0,1fr)']"
          divider="inset"
          class="list-gap-3 list-row-px-4 rounded-lg border border-outline-gray-1"
          data-testid="machines"
        >
          <ListRows :items="portal.machines" v-slot="{ item: m }">
            <ListRow class="min-h-17 py-3">
              <ListCell>
                <span class="lucide-truck size-5 text-ink-gray-5" aria-hidden="true" />
              </ListCell>
              <ListCell>
                <div class="min-w-0">
                  <p class="truncate font-medium">{{ m.equipment_name || m.name }}</p>
                  <p v-if="m.project" class="truncate text-sm text-ink-gray-5">{{ m.project }}</p>
                </div>
              </ListCell>
            </ListRow>
          </ListRows>
        </List>
      </section>

      <RouterLink
        :to="{ name: 'Requests' }"
        class="flex min-h-[3.5rem] items-center justify-between rounded-lg border border-outline-gray-1 p-4"
      >
        <span>{{ __('My requests') }}</span>
        <span class="flex items-center gap-2">
          <StatusBadge v-if="pending.length" status="Pending" />
          <span class="text-ink-gray-5">{{ portal.requests.length }}</span>
          <span
            class="lucide-chevron-right size-4 text-ink-gray-5 rtl:rotate-180"
            aria-hidden="true"
          />
        </span>
      </RouterLink>

      <a
        v-if="reviewer"
        href="/app/equipment-needs-review"
        class="flex min-h-[3.5rem] items-center justify-between rounded-lg border border-outline-gray-1 p-4"
      >
        <span>{{ __('Equipment Needs Review') }}</span>
        <span class="lucide-external-link size-4 text-ink-gray-5" aria-hidden="true" />
      </a>
    </template>
  </div>
</template>
