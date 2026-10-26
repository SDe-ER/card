<script setup lang="ts">
import { ref, watch } from 'vue'
import { Button, Combobox, ErrorMessage } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import CatalogDialog from '../components/CatalogDialog.vue'
import { searchMachines } from '../data/catalog'
import { __ } from '../i18n'

// Read-only catalog: choose a machine the server lets you see, then browse the catalogue with
// each item's fit for it. Nothing is requested or changed from here.
const machine = ref<string | null>(null)
const query = ref('')
const options = ref<{ value: string; label: string }[]>([])
const error = ref('')
const browsing = ref(false)
let request = 0

async function loadMachines() {
  const current = ++request
  // after a pick the Combobox shows the option's label in the query; that is not a new search
  const picked = options.value.find((o) => o.value === machine.value)
  const txt = picked && query.value === picked.label ? '' : query.value
  try {
    const page = await searchMachines(txt)
    if (current !== request) return
    error.value = ''
    options.value = page.machines.map((m) => ({
      value: m.name,
      label: [m.equipment_name || m.name, m.model].filter(Boolean).join(' · '),
    }))
  } catch (e) {
    if (current === request) error.value = (e as Error).message
  }
}

loadMachines()
let timer: ReturnType<typeof setTimeout> | undefined
watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(loadMachines, 300)
})
</script>

<template>
  <TopBar :title="__('Catalog', [], 'Card Mobile')" />
  <div class="space-y-4 p-4">
    <Combobox
      v-model="machine"
      v-model:query="query"
      :options="options"
      :filterable="false"
      :placeholder="__('Equipment', [], 'Card Mobile')"
      data-testid="machine"
    />
    <ErrorMessage :message="error" />
    <Button
      class="h-12 w-full"
      size="lg"
      variant="solid"
      icon-left="lucide-book-open"
      :disabled="!machine"
      :label="__('Browse catalog', [], 'Card Mobile')"
      @click="browsing = true"
    />
    <CatalogDialog v-model:open="browsing" :equipment="machine" readonly />
  </div>
</template>
