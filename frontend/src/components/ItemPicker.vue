<script setup lang="ts">
import { ref, watch } from 'vue'
import { Button, FormControl } from 'frappe-ui'
import CatalogDialog from './CatalogDialog.vue'
import FitBadge from './FitBadge.vue'
import { fitFor, needsFitReason } from '../data/catalog'
import { searchItems, type DraftLine, type Item } from '../data/needs'
import { __ } from '../i18n'

// Pick an ERPNext Item, or keep the typed text as the description when nothing fits. A picked
// Item shows its fit for the machine; without a confirmed fit the line needs a reason (Q10).
const line = defineModel<DraftLine>({ required: true })
const props = defineProps<{ equipment?: string | null }>()
const text = ref(line.value.item_name || line.value.description)
const results = ref<Item[]>([])
const browsing = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

watch(text, (value) => {
  if (value !== line.value.item_name) {
    line.value.item_code = ''
    line.value.item_name = ''
  }
  line.value.description = value
  clearTimeout(timer)
  if (value.trim().length < 2 || line.value.item_code) {
    results.value = []
    return
  }
  timer = setTimeout(async () => {
    results.value = await searchItems(value.trim()).catch(() => [])
  }, 300)
})

function pick(item: Item) {
  line.value.item_code = item.item_code
  line.value.item_name = item.item_name || item.item_code
  text.value = line.value.item_name
  results.value = []
}

// the fit is asked again whenever the item or the machine changes; only the latest answer counts
let fitRequest = 0
watch(
  () => [line.value.item_code, props.equipment] as const,
  async ([code, equipment]) => {
    const current = ++fitRequest
    line.value.fit = null
    if (!code || !equipment) return
    const fits = await fitFor(equipment, [code]).catch(() => null)
    // no answer counts as no fitment record: the reason is asked, never skipped
    if (current === fitRequest) line.value.fit = fits?.[code]?.fit ?? 'unknown'
  },
  { immediate: true },
)
</script>

<template>
  <div class="relative">
    <FormControl
      v-model="text"
      type="text"
      size="lg"
      :placeholder="__('Search an item or describe it')"
      autocomplete="off"
    />
    <div class="mt-1 flex items-center justify-between gap-2">
      <span class="text-xs text-ink-gray-5">{{ line.item_code }}</span>
      <Button
        variant="ghost"
        size="sm"
        icon-left="lucide-book-open"
        :label="__('Browse catalog', [], 'Card Mobile')"
        @click="browsing = true"
      />
    </div>
    <div v-if="line.item_code && equipment" class="mt-2 space-y-2">
      <FitBadge v-if="line.fit" :fit="line.fit" />
      <FormControl
        v-if="needsFitReason(line.fit)"
        v-model="line.fit_reason"
        type="textarea"
        :rows="2"
        :label="__('Why this item without a confirmed fit?')"
        maxlength="500"
        required
      />
    </div>
    <CatalogDialog v-model:open="browsing" :equipment="equipment" @pick="pick" />
    <ul
      v-if="results.length"
      class="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-outline-gray-2 bg-surface-base shadow-lg"
    >
      <li v-for="item in results" :key="item.item_code">
        <button
          type="button"
          class="block min-h-[3rem] w-full px-3 py-2 text-start"
          @click="pick(item)"
        >
          <span class="block">{{ item.item_name }}</span>
          <span class="block text-xs text-ink-gray-5"
            >{{ item.item_code }} · {{ item.stock_uom }}</span
          >
        </button>
      </li>
    </ul>
  </div>
</template>
