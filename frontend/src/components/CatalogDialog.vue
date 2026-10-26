<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  Avatar,
  Button,
  Combobox,
  Dialog,
  ErrorMessage,
  LoadingIndicator,
  Switch,
  TextInput,
} from 'frappe-ui'
import FitBadge from './FitBadge.vue'
import {
  filterOptions,
  mergePage,
  searchCatalog,
  type CatalogItem,
  type FilterOption,
} from '../data/catalog'
import type { Item } from '../data/needs'
import { __ } from '../i18n'

// Browse the ERPNext catalogue: the server searches, filters and pages; this only shows the rows.
// With a machine every row shows its fit, and "Fits this machine" lists only confirmed fits.
// Read only: rows cannot be picked (the catalog viewer of a Card User).
const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ equipment?: string | null; readonly?: boolean }>()
const emit = defineEmits<{ pick: [item: Item] }>()
const fits = ref(false)

const txt = ref('')
const itemGroup = ref<string | null>(null)
const brand = ref<string | null>(null)
const groupQuery = ref('')
const brandQuery = ref('')
const groupOptions = ref<FilterOption[]>([])
const brandOptions = ref<FilterOption[]>([])
const items = ref<CatalogItem[]>([])
const hasMore = ref(false)
const loading = ref(false)
const error = ref('')
let request = 0

async function load(more = false) {
  const current = ++request
  loading.value = true
  error.value = ''
  try {
    const page = await searchCatalog(
      {
        txt: txt.value,
        item_group: itemGroup.value,
        brand: brand.value,
        equipment: props.equipment,
        fits: fits.value,
      },
      more ? items.value.length : 0,
    )
    if (current !== request) return
    items.value = more ? mergePage(items.value, page.items) : page.items
    hasMore.value = page.has_more
  } catch (e) {
    if (current === request) error.value = (e as Error).message
  } finally {
    if (current === request) loading.value = false
  }
}

// After a pick the Combobox puts the option's label in the query; that is not a new search.
function optionQuery(query: string, value: string | null, options: FilterOption[]) {
  const picked = options.find((o) => o.value === value)
  return picked && query === picked.label ? '' : query
}

// only the answer to the latest query is shown
let groupRequest = 0
let brandRequest = 0

async function loadGroups() {
  const current = ++groupRequest
  const query = optionQuery(groupQuery.value, itemGroup.value, groupOptions.value)
  const options = await filterOptions('item_group', query).catch(() => null)
  if (current === groupRequest && options) groupOptions.value = options
}

async function loadBrands() {
  const current = ++brandRequest
  const query = optionQuery(brandQuery.value, brand.value, brandOptions.value)
  const options = await filterOptions('brand', query).catch(() => null)
  if (current === brandRequest && options) brandOptions.value = options
}

// nothing is fetched until the dialog opens (every request line has its own picker)
watch(open, (value) => {
  if (!value) return
  load()
  loadGroups()
  loadBrands()
})
watch([txt, itemGroup, brand, fits, () => props.equipment], () => open.value && load())
watch(groupQuery, () => open.value && loadGroups())
watch(brandQuery, () => open.value && loadBrands())

function pick(item: { item_code: string; item_name: string }, uom = '') {
  if (props.readonly) return
  emit('pick', { item_code: item.item_code, item_name: item.item_name, stock_uom: uom })
  open.value = false
}
</script>

<template>
  <Dialog v-model:open="open" :title="__('Catalog', [], 'Card Mobile')" size="3xl">
    <div class="space-y-3">
      <TextInput
        v-model="txt"
        type="search"
        size="lg"
        :debounce="300"
        :placeholder="__('Search by name, code, barcode or OEM number', [], 'Card Mobile')"
        autocomplete="off"
      />
      <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Combobox
          v-model="itemGroup"
          v-model:query="groupQuery"
          :options="groupOptions"
          :filterable="false"
          :placeholder="__('Item group', [], 'Card Mobile')"
        />
        <Combobox
          v-model="brand"
          v-model:query="brandQuery"
          :options="brandOptions"
          :filterable="false"
          :placeholder="__('Brand', [], 'Card Mobile')"
        />
      </div>
      <Switch
        v-if="equipment"
        v-model="fits"
        :label="__('Fits this machine')"
        data-testid="fits-switch"
      />
      <ErrorMessage :message="error" />
      <ul class="divide-y divide-outline-gray-1">
        <li v-for="item in items" :key="item.item_code" class="py-2">
          <component
            :is="readonly ? 'div' : 'button'"
            :type="readonly ? undefined : 'button'"
            class="flex min-h-[3.5rem] w-full items-center gap-3 text-start"
            @click="pick(item, item.stock_uom)"
          >
            <Avatar :image="item.image || undefined" :label="item.item_name" shape="square" size="xl" />
            <div class="min-w-0">
              <span class="block truncate text-ink-gray-8">{{ item.item_name }}</span>
              <span class="block truncate text-xs text-ink-gray-5"
                >{{ item.item_code }} · {{ item.stock_uom }}</span
              >
              <span
                v-if="item.item_group_label || item.brand"
                class="block truncate text-xs text-ink-gray-5"
                >{{ [item.item_group_label, item.brand].filter(Boolean).join(' · ') }}</span
              >
              <span v-if="item.oem.length" class="block truncate text-xs text-ink-gray-5"
                >{{ __('OEM', [], 'Card Mobile') }}:
                {{ item.oem.map((o) => `${o.part_no} (${o.manufacturer})`).join(', ') }}</span
              >
              <FitBadge v-if="item.fit" class="mt-1" :fit="item.fit" :model="item.fit_model" />
            </div>
          </component>
          <div v-if="item.alternatives.length" class="mt-1 flex flex-wrap items-center gap-1 ps-14">
            <span class="text-xs text-ink-gray-5">{{ __('Alternatives', [], 'Card Mobile') }}:</span>
            <Button
              v-for="alt in item.alternatives"
              :key="alt.item_code"
              size="sm"
              variant="subtle"
              :label="alt.item_name"
              :disabled="readonly"
              @click="pick(alt)"
            />
          </div>
        </li>
      </ul>
      <p
        v-if="!loading && !error && !items.length"
        class="px-3 py-10 text-center text-sm text-ink-gray-4"
      >
        {{ __('No items found.', [], 'Card Mobile') }}
      </p>
      <div v-if="loading" class="flex justify-center py-3"><LoadingIndicator class="size-5" /></div>
      <Button
        v-else-if="hasMore"
        class="w-full"
        :label="__('Load more', [], 'Card Mobile')"
        @click="load(true)"
      />
    </div>
  </Dialog>
</template>
