<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'

const props = defineProps<{ status: string }>()

const theme = computed(() => {
  if (props.status === 'Approved') return 'green'
  if (props.status === 'Rejected') return 'red'
  if (props.status === 'In review') return 'blue'
  return 'amber'
})
</script>

<template>
  <Badge :theme="theme" size="md" :label="__(status || 'Pending', [], 'Card Mobile')" />
</template>
