<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { logState, stateLabel, stateTheme, type DailyLog } from '../data/dailyLog'
import { __ } from '../i18n'

// FR-150: the state of a daily log as the server stored it (draft, or its approval status). A
// cancelled returned log without its corrected draft says so (`correctionDue`).
const props = defineProps<{
  log: Pick<DailyLog, 'docstatus' | 'approval_status'>
  correctionDue?: boolean
}>()
const state = computed(() => logState(props.log))
</script>

<template>
  <Badge
    v-if="correctionDue"
    theme="red"
    size="md"
    :label="__('Corrected draft missing')"
    data-state="CorrectionDue"
    data-testid="log-state"
  />
  <Badge
    v-else
    :theme="stateTheme(state)"
    size="md"
    :label="stateLabel(state)"
    :data-state="state"
    data-testid="log-state"
  />
</template>
