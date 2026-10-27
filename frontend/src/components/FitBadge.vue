<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import type { Fit } from '../data/catalog'
import { __ } from '../i18n'

// The fit of an Item for the chosen machine. A pending review and no fitment record are not a
// fit (O6) and look different from a confirmed one; Not compatible is a warning.
const props = defineProps<{ fit: Fit; model?: string | null }>()

const theme = computed(
  () =>
    (
      ({
        confirmed_machine: 'green',
        confirmed_model: 'green',
        not_compatible: 'red',
        pending: 'amber',
        unknown: 'gray',
      }) as const
    )[props.fit] ?? 'gray',
)

const label = computed(() => {
  if (props.fit === 'confirmed_machine') return __('Confirmed for this machine')
  if (props.fit === 'confirmed_model') return __('Confirmed for model {0}', [props.model || ''])
  if (props.fit === 'not_compatible') return __('Not compatible with this machine')
  if (props.fit === 'pending') return __('Fit pending technical review')
  return __('No fitment record')
})
</script>

<template>
  <Badge :theme="theme" variant="subtle" size="md" :label="label">
    <template v-if="fit === 'not_compatible'" #prefix>
      <span class="lucide-triangle-alert size-3" aria-hidden="true" />
    </template>
  </Badge>
</template>
