<script setup lang="ts">
import { ref } from 'vue'
import { ErrorMessage, LoadingIndicator } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import { formatMoney } from '../data/home'
import { listProjects, type ProjectRow } from '../data/management'

const rows = ref<ProjectRow[] | null>(null)
const error = ref('')
listProjects()
  .then((r) => (rows.value = r))
  .catch((e: Error) => (error.value = e.message))
</script>

<template>
  <TopBar :title="__('Projects', [], 'Card Mobile')" back />
  <div class="space-y-4 p-4">
    <ErrorMessage :message="error" />
    <LoadingIndicator v-if="!rows && !error" class="mx-auto size-6" />
    <p v-else-if="rows && !rows.length" class="rounded-xl bg-surface-gray-1 p-4 text-ink-gray-6">
      {{ __('No projects found.', [], 'Card Mobile') }}
    </p>
    <div v-else-if="rows" class="space-y-3" data-testid="projects">
      <div
        v-for="row in rows"
        :key="row.project ?? ''"
        class="space-y-2 rounded-xl border border-outline-gray-1 p-3"
      >
        <p class="truncate font-medium">
          {{ row.project || __('No project', [], 'Card Mobile') }}
        </p>
        <p class="text-sm text-ink-gray-5">
          {{ __('Equipment', [], 'Card Mobile') }} {{ row.equipment }} ·
          {{ __('Cards', [], 'Card Mobile') }} {{ row.cards }} ·
          {{ __('Hours', [], 'Card Mobile') }} {{ row.hours }}
        </p>
        <div
          v-if="row.result !== undefined"
          class="text-sm tabular-nums"
          data-testid="money"
          dir="ltr"
        >
          <p>{{ __('Revenue', [], 'Card Mobile') }} {{ formatMoney(row.revenue ?? 0, null) }}</p>
          <p>{{ __('Cost', [], 'Card Mobile') }} {{ formatMoney(row.cost ?? 0, null) }}</p>
          <p class="font-medium">
            {{ __('Result', [], 'Card Mobile') }} {{ formatMoney(row.result, null) }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
