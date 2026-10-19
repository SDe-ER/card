<script setup lang="ts">
import { ref, watch } from 'vue'
import { FormControl } from 'frappe-ui'
import { searchItems, type DraftLine, type Item } from '../data/needs'
import { __ } from '../i18n'

// Pick an ERPNext Item, or keep the typed text as the description when nothing fits.
const line = defineModel<DraftLine>({ required: true })
const text = ref(line.value.item_name || line.value.description)
const results = ref<Item[]>([])
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
    <span v-if="line.item_code" class="mt-1 block text-xs text-ink-gray-5">{{
      line.item_code
    }}</span>
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
