<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { logState, stateLabel, stateTheme, type DailyLog } from '../data/dailyLog'

// FR-150: the state of a daily log as the server stored it (draft, or its approval status).
const props = defineProps<{ log: Pick<DailyLog, 'docstatus' | 'approval_status'> }>()
const state = computed(() => logState(props.log))
</script>

<template>
  <Badge
    :theme="stateTheme(state)"
    size="md"
    :label="stateLabel(state)"
    :data-state="state"
    data-testid="log-state"
  />
</template>
