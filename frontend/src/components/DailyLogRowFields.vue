<script setup lang="ts">
import { computed } from 'vue'
import { Button, FormControl } from 'frappe-ui'
import type { DailyLogRow, StopReason } from '../data/dailyLog'
import { __ } from '../i18n'

// FR-150: the hours of one equipment on the daily log. The stop reason is offered only to users who
// may read the company's stop reasons (`reasons` is null for an operator); a stored reason is kept.
const row = defineModel<DailyLogRow>({ required: true })
const props = defineProps<{
  label: string
  index: number
  reasons: StopReason[] | null
  removable: boolean
}>()
defineEmits<{ remove: [] }>()

const reasonOptions = computed(() => [
  { label: __('No stop reason'), value: '' },
  ...(props.reasons ?? []).map((r) => ({ label: r.reason_name || r.name, value: r.name })),
])
const stopReason = computed({
  get: () => row.value.stop_reason || '',
  set: (value: string) => (row.value.stop_reason = value || null),
})
</script>

<template>
  <section class="space-y-3 rounded-lg border border-outline-gray-1 p-3" data-testid="log-row">
    <div class="flex items-center justify-between gap-2">
      <p class="min-w-0 truncate font-medium">
        <span
          class="lucide-truck me-2 inline-block size-4 align-middle text-ink-gray-5"
          aria-hidden="true"
        />{{ label }}
      </p>
      <Button
        v-if="removable"
        variant="ghost"
        icon="lucide-trash-2"
        class="size-11"
        :aria-label="__('Remove', [], 'Card Mobile')"
        @click="$emit('remove')"
      />
    </div>
    <div class="grid grid-cols-3 items-end gap-2">
      <FormControl
        v-model="row.day_hours"
        type="number"
        size="lg"
        :label="__('Day shift hours')"
        min="0"
        max="24"
        step="any"
        inputmode="decimal"
        :data-testid="`day-${index}`"
      />
      <FormControl
        v-model="row.night_hours"
        type="number"
        size="lg"
        :label="__('Night shift hours')"
        min="0"
        max="24"
        step="any"
        inputmode="decimal"
      />
      <FormControl
        v-model="row.stopped_hours"
        type="number"
        size="lg"
        :label="__('Stopped hours')"
        min="0"
        max="24"
        step="any"
        inputmode="decimal"
      />
    </div>
    <FormControl
      v-if="reasons"
      v-model="stopReason"
      type="select"
      size="lg"
      :label="__('Stop reason')"
      :options="reasonOptions"
    />
    <FormControl
      v-model="row.notes"
      type="textarea"
      :rows="2"
      :label="__('Notes', [], 'Card Mobile')"
      maxlength="500"
    />
  </section>
</template>
