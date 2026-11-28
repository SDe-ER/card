<script setup lang="ts">
import { ref } from 'vue'
import { ErrorMessage, LoadingIndicator } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import { formatMoney } from '../data/home'
import { getManagementContext, listMonthlyCards, type CardRow } from '../data/management'

const rows = ref<CardRow[] | null>(null)
const error = ref('')
// a Card Supervisor has no read right on monthly cards: say so instead of an empty month
const available = ref(true)
getManagementContext()
  .then((c) => (available.value = c.cards))
  .catch(() => null)
listMonthlyCards()
  .then((r) => (rows.value = r))
  .catch((e: Error) => (error.value = e.message))
</script>

<template>
  <TopBar :title="__('Monthly cards', [], 'Card Mobile')" back />
  <div class="space-y-4 p-4">
    <ErrorMessage :message="error" />
    <p
      v-if="!available"
      class="rounded-xl bg-surface-gray-1 p-4 text-ink-gray-6"
      data-testid="no-cards-right"
    >
      {{ __('Monthly cards are not available for your role.', [], 'Card Mobile') }}
    </p>
    <LoadingIndicator v-else-if="!rows && !error" class="mx-auto size-6" />
    <p v-else-if="rows && !rows.length" class="rounded-xl bg-surface-gray-1 p-4 text-ink-gray-6">
      {{ __('No monthly cards this month.', [], 'Card Mobile') }}
    </p>
    <ul
      v-else-if="rows"
      class="divide-y divide-outline-gray-1 rounded-xl border border-outline-gray-1"
      data-testid="cards"
    >
      <li v-for="row in rows" :key="row.name" class="p-3">
        <p class="truncate font-medium">{{ row.equipment_name || row.equipment }}</p>
        <p class="truncate text-sm text-ink-gray-5">
          {{
            [row.project, row.total_working_hours + ' ' + __('Hours', [], 'Card Mobile')]
              .filter(Boolean)
              .join(' · ')
          }}
        </p>
        <p
          v-if="row.net_amount !== undefined"
          class="text-sm tabular-nums"
          data-testid="amount"
          dir="ltr"
        >
          {{ formatMoney(row.net_amount, null) }}
        </p>
      </li>
    </ul>
  </div>
</template>
