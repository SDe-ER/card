<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button, ErrorMessage, LoadingIndicator } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import DailyLogBadge from '../components/DailyLogBadge.vue'
import { errorText, listMyLogs, type DailyLogSummary } from '../data/dailyLog'
import { getSessionContext } from '../data/session'

// FR-150: the daily logs the signed-in user created (drafts and submitted; cancelled ones are
// replaced by their amendment). The server lists only what the user may read.
const route = useRoute()
const logs = ref<DailyLogSummary[] | null>(null)
const error = ref('')

async function load() {
  error.value = ''
  try {
    const ctx = await getSessionContext()
    logs.value = ctx ? await listMyLogs(ctx.user) : []
  } catch (e) {
    error.value = errorText(e)
  }
}
load()
</script>

<template>
  <TopBar :title="__('My daily logs')" />
  <div class="space-y-3 p-4">
    <p
      v-if="route.query.submitted"
      class="rounded-lg bg-surface-green-1 p-3 text-ink-green-3"
      role="status"
    >
      {{ __('Your daily log was sent to the supervisor.') }}
    </p>
    <Button
      class="h-12 w-full"
      size="lg"
      variant="solid"
      icon-left="lucide-circle-plus"
      :label="__('New daily log')"
      :route="{ name: 'DailyLogNew' }"
    />
    <LoadingIndicator v-if="!logs && !error" class="mx-auto size-6" />
    <ErrorMessage :message="error" data-testid="error" />
    <Button
      v-if="error"
      class="w-full"
      :label="__('Try again', [], 'Card Mobile')"
      @click="load"
    />
    <p v-if="logs && !logs.length" class="rounded-lg bg-surface-gray-1 p-4 text-ink-gray-6">
      {{ __('No daily logs yet.') }}
    </p>
    <RouterLink
      v-for="log in logs ?? []"
      :key="log.name"
      :to="{ name: 'DailyLogView', params: { name: log.name } }"
      class="flex min-h-[3.5rem] items-center justify-between gap-3 rounded-lg border border-outline-gray-1 p-4"
      data-testid="daily-log"
    >
      <div class="min-w-0">
        <p class="truncate font-medium">{{ log.project }}</p>
        <p class="text-xs text-ink-gray-5">
          <bdi dir="ltr" class="tabular-nums">{{ log.log_date }}</bdi> ·
          <bdi class="whitespace-nowrap">{{ log.name }}</bdi>
        </p>
      </div>
      <span class="flex shrink-0 items-center gap-2">
        <DailyLogBadge :log="log" />
        <span
          class="lucide-chevron-right size-4 text-ink-gray-5 rtl:rotate-180"
          aria-hidden="true"
        />
      </span>
    </RouterLink>
  </div>
</template>
