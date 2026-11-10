<script setup lang="ts">
import { computed } from 'vue'
import { Button, ErrorMessage } from 'frappe-ui'
import DailyLogBadge from './DailyLogBadge.vue'
import { actionsFor, logState, type DailyLog } from '../data/dailyLog'

// FR-150: what CARD Mobile shows of one daily log: its state as the server stored it, its rows
// (hours only: a daily log has no money field, O-20) and the actions offered for it (actionsFor).
// Approving, verifying and returning are never offered here, for any role; reviewers get a link
// to the log in CARD Desk, where the server checks the separation of duties.
const props = defineProps<{
  log: DailyLog
  roles: string[]
  error?: string
  busy?: boolean
  saved?: boolean
}>()
defineEmits<{ submit: []; correct: [] }>()

const actions = computed(() => actionsFor(props.log, props.roles))
const state = computed(() => logState(props.log))
const deskUrl = computed(() => `/app/card-daily-log/${encodeURIComponent(props.log.name)}`)

function hours(value: number | null | undefined) {
  return Number(value || 0).toLocaleString('en-US', { maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="space-y-4 p-4" data-testid="daily-log-detail">
    <p
      v-if="saved && state === 'Draft'"
      class="rounded-lg bg-surface-green-1 p-3 text-ink-green-3"
      role="status"
    >
      {{ __('Draft saved. Send it to the supervisor when it is complete.') }}
    </p>

    <section class="space-y-2 rounded-lg border border-outline-gray-1 p-4">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <p class="truncate font-medium">{{ log.project }}</p>
          <p class="text-xs text-ink-gray-5">
            <bdi dir="ltr" class="tabular-nums">{{ log.log_date }}</bdi> ·
            <bdi class="whitespace-nowrap">{{ log.name }}</bdi>
          </p>
        </div>
        <DailyLogBadge :log="log" />
      </div>
      <p v-if="state === 'Draft'" class="text-sm text-ink-gray-6" data-testid="state-help">
        {{ __('Not sent yet. You can still change it.') }}
      </p>
      <p
        v-else-if="state === 'Pending' || state === 'Verified'"
        class="text-sm text-ink-gray-6"
        data-testid="state-help"
      >
        {{ __('Sent to the supervisor. Waiting for approval.') }}
      </p>
      <p v-else-if="state === 'Approved'" class="text-sm text-ink-gray-6" data-testid="state-help">
        {{ __('Approved. It can no longer be changed.') }}
      </p>
      <div
        v-else-if="state === 'Returned'"
        class="space-y-1 rounded bg-surface-red-1 p-3 text-sm text-ink-red-4"
        data-testid="state-help"
      >
        <p class="font-medium">{{ __('Returned for correction') }}</p>
        <p
          v-if="log.return_reason"
          dir="auto"
          class="whitespace-pre-line"
          data-testid="return-reason"
        >
          {{ log.return_reason }}
        </p>
      </div>
      <p v-if="log.notes" dir="auto" class="whitespace-pre-line text-sm text-ink-gray-7">
        {{ log.notes }}
      </p>
    </section>

    <section
      v-for="row in log.rows"
      :key="row.name || row.equipment"
      class="space-y-2 rounded-lg border border-outline-gray-1 p-4"
      data-testid="log-row"
    >
      <p class="truncate font-medium">{{ row.equipment_name || row.equipment }}</p>
      <dl class="grid grid-cols-3 items-end gap-2 text-sm">
        <div>
          <dt class="text-xs text-ink-gray-5">{{ __('Day shift hours') }}</dt>
          <dd>
            <bdi dir="ltr" class="tabular-nums">{{ hours(row.day_hours) }}</bdi>
          </dd>
        </div>
        <div>
          <dt class="text-xs text-ink-gray-5">{{ __('Night shift hours') }}</dt>
          <dd>
            <bdi dir="ltr" class="tabular-nums">{{ hours(row.night_hours) }}</bdi>
          </dd>
        </div>
        <div>
          <dt class="text-xs text-ink-gray-5">{{ __('Stopped hours') }}</dt>
          <dd>
            <bdi dir="ltr" class="tabular-nums">{{ hours(row.stopped_hours) }}</bdi>
          </dd>
        </div>
      </dl>
      <p v-if="row.stop_reason" class="text-sm text-ink-gray-6">
        {{ __('Stop reason') }}: {{ row.stop_reason }}
      </p>
      <p v-if="row.notes" dir="auto" class="whitespace-pre-line text-sm text-ink-gray-6">
        {{ row.notes }}
      </p>
    </section>

    <ErrorMessage :message="error" data-testid="error" />

    <div class="space-y-3" data-testid="actions">
      <Button
        v-if="actions.includes('submit')"
        class="h-12 w-full"
        size="lg"
        variant="solid"
        icon-left="lucide-send"
        :loading="busy"
        :label="__('Send to supervisor')"
        data-action="submit"
        @click="$emit('submit')"
      />
      <Button
        v-if="actions.includes('edit')"
        class="h-12 w-full"
        size="lg"
        icon-left="lucide-pencil"
        :label="__('Edit', [], 'Card Mobile')"
        :route="{ name: 'DailyLogEdit', params: { name: log.name } }"
        data-action="edit"
      />
      <Button
        v-if="actions.includes('correct')"
        class="h-12 w-full"
        size="lg"
        variant="solid"
        icon-left="lucide-pencil"
        :label="__('Correct this daily log')"
        data-action="correct"
        @click="$emit('correct')"
      />
      <a
        v-if="actions.includes('desk')"
        :href="deskUrl"
        class="flex min-h-[3.5rem] items-center justify-between rounded-lg border border-outline-gray-1 p-4"
        data-action="desk"
      >
        <span>{{ __('Open in CARD Desk') }}</span>
        <span class="lucide-external-link size-4 text-ink-gray-5" aria-hidden="true" />
      </a>
    </div>
  </div>
</template>
