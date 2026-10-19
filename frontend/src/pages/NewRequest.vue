<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, ErrorMessage, FormControl, LoadingIndicator, TabButtons } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import ItemPicker from '../components/ItemPicker.vue'
import {
  getPortal,
  incompleteLines,
  newLine,
  sendableLines,
  submitNeeds,
  type PortalContext,
} from '../data/needs'
import { __ } from '../i18n'

const router = useRouter()
const portal = ref<PortalContext | null>(null)
const equipment = ref('')
const lines = ref([newLine()])
const notes = ref('')
const error = ref('')
const sending = ref(false)

getPortal()
  .then((p) => {
    portal.value = p
    if (p.machines.length === 1) equipment.value = p.machines[0].name
  })
  .catch((e: Error) => (error.value = e.message))

const machineOptions = computed(() =>
  (portal.value?.machines ?? []).map((m) => ({
    value: m.name,
    label: m.project ? `${m.equipment_name || m.name} — ${m.project}` : m.equipment_name || m.name,
  })),
)
const kinds = [
  { label: __('Part or consumable'), value: 'Part' },
  { label: __('Tool'), value: 'Tool' },
]

async function send() {
  error.value = ''
  const incomplete = incompleteLines(lines.value)
  if (incomplete.length) {
    error.value = __(
      'Line {0} needs an item and a quantity.',
      [incomplete.join(', ')],
      'Card Mobile',
    )
    return
  }
  if (!sendableLines(lines.value).length) {
    error.value = __('Add at least one line with a quantity.')
    return
  }
  sending.value = true
  try {
    await submitNeeds(equipment.value, lines.value, notes.value)
  } catch (e) {
    error.value = (e as Error).message
    return
  } finally {
    sending.value = false
  }
  // Sent. A failed list refresh must not look like a failed send (it would invite a second one).
  getPortal(true).catch(() => null)
  router.replace({ name: 'Requests', query: { sent: '1' } })
}
</script>

<template>
  <TopBar :title="__('New request')" back />
  <LoadingIndicator v-if="!portal && !error" class="mx-auto mt-8 size-6" />
  <ErrorMessage v-if="!portal" class="m-4" :message="error" />
  <p
    v-else-if="!portal.machines.length"
    class="m-4 rounded-lg bg-surface-gray-1 p-4 text-ink-gray-6"
  >
    {{ __('No equipment is assigned to you this month.') }}
  </p>
  <form v-else class="space-y-5 p-4" autocomplete="off" @submit.prevent="send">
    <FormControl
      v-model="equipment"
      type="select"
      size="lg"
      :label="__('Equipment', [], 'Card Mobile')"
      :options="machineOptions"
      :placeholder="__('Equipment', [], 'Card Mobile')"
      required
    />

    <section
      v-for="(line, i) in lines"
      :key="line.key"
      class="space-y-3 rounded-lg border border-outline-gray-1 p-3"
      data-testid="line"
    >
      <div class="flex items-center justify-between gap-2">
        <TabButtons v-model="line.kind" :buttons="kinds" />
        <Button
          v-if="lines.length > 1"
          variant="ghost"
          icon="lucide-trash-2"
          :aria-label="__('Remove', [], 'Card Mobile')"
          @click="lines.splice(i, 1)"
        />
      </div>
      <ItemPicker v-model="lines[i]" />
      <div class="grid grid-cols-[7rem_1fr] gap-3">
        <FormControl
          v-model="line.qty"
          type="number"
          size="lg"
          :label="__('Quantity', [], 'Card Mobile')"
          min="0"
          step="any"
        />
        <FormControl
          v-model="line.reason"
          type="text"
          size="lg"
          :label="__('Reason', [], 'Card Mobile')"
          maxlength="140"
        />
      </div>
    </section>

    <Button
      class="h-12 w-full"
      size="lg"
      icon-left="lucide-plus"
      :label="__('Add a line')"
      @click="lines.push(newLine())"
    />

    <FormControl
      v-model="notes"
      type="textarea"
      :label="__('Notes', [], 'Card Mobile')"
      :rows="2"
    />

    <ErrorMessage :message="error" />
    <Button
      class="h-12 w-full"
      size="lg"
      variant="solid"
      type="submit"
      :disabled="!equipment"
      :loading="sending"
      :label="__('Send to supervisor')"
    />
  </form>
</template>
