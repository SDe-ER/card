<script setup lang="ts">
import { ref, watch } from 'vue'
import { ErrorMessage, LoadingIndicator } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import {
  getManagementContext,
  listAllEquipment,
  type FleetRow,
  type ManagementContext,
} from '../data/management'

const ctx = ref<ManagementContext | null>(null)
const rows = ref<FleetRow[] | null>(null)
const ownership = ref('')
const error = ref('')

getManagementContext()
  .then((c) => (ctx.value = c))
  .catch((e: Error) => (error.value = e.message))

watch(
  ownership,
  (value) => {
    rows.value = null
    listAllEquipment({ ownership: value })
      .then((r) => (rows.value = r))
      .catch((e: Error) => (error.value = e.message))
  },
  { immediate: true },
)
</script>

<template>
  <TopBar :title="__('Fleet', [], 'Card Mobile')" back />
  <div class="space-y-4 p-4">
    <ErrorMessage :message="error" />
    <div v-if="ctx?.ownership.length" class="flex flex-wrap gap-2" data-testid="ownership-filter">
      <button
        v-for="option in ['', ...ctx.ownership]"
        :key="option"
        type="button"
        class="min-h-11 rounded-lg border border-outline-gray-1 px-3 text-sm"
        :class="ownership === option ? 'bg-surface-gray-3 font-medium' : ''"
        @click="ownership = option"
      >
        {{ option || __('All', [], 'Card Mobile') }}
      </button>
    </div>
    <LoadingIndicator v-if="!rows && !error" class="mx-auto size-6" />
    <p v-else-if="rows && !rows.length" class="rounded-xl bg-surface-gray-1 p-4 text-ink-gray-6">
      {{ __('No equipment found.', [], 'Card Mobile') }}
    </p>
    <ul
      v-else-if="rows"
      class="divide-y divide-outline-gray-1 rounded-xl border border-outline-gray-1"
      data-testid="fleet"
    >
      <li v-for="row in rows" :key="row.name" class="p-3">
        <p class="truncate font-medium">{{ row.equipment_name || row.name }}</p>
        <p class="truncate text-sm text-ink-gray-5">
          {{ [row.current_project, row.ownership, row.operator_name].filter(Boolean).join(' · ') }}
        </p>
      </li>
    </ul>
  </div>
</template>
