<script setup lang="ts">
import { computed, ref } from 'vue'
import { getSessionContext } from '../data/session'
import { __ } from '../i18n'

const profile = { to: { name: 'Profile' }, icon: 'lucide-circle-user', label: __('Profile', [], 'Card Mobile') }
const operatorItems = [
  { to: { name: 'Home' }, icon: 'lucide-house', label: __('Home', [], 'Card Mobile') },
  { to: { name: 'NewRequest' }, icon: 'lucide-circle-plus', label: __('New request') },
  { to: { name: 'Requests' }, icon: 'lucide-list-checks', label: __('My requests') },
  profile,
]
// a catalog viewer (Card User) has no requests
const viewerItems = [
  { to: { name: 'Catalog' }, icon: 'lucide-book-open', label: __('Catalog', [], 'Card Mobile') },
  profile,
]
// shown once the session is known, so a catalog viewer never sees the operator tabs
const catalogOnly = ref<boolean | null>(null)
getSessionContext()
  .then((ctx) => (catalogOnly.value = !!ctx?.catalog_only))
  .catch(() => (catalogOnly.value = false))
const items = computed(() =>
  catalogOnly.value === null ? [] : catalogOnly.value ? viewerItems : operatorItems,
)
</script>

<template>
  <nav
    class="bottom-nav fixed bottom-0 left-1/2 z-10 w-full max-w-[480px] -translate-x-1/2 border-t border-outline-gray-1 bg-surface-base"
  >
    <ul class="grid" :class="items.length === 4 ? 'grid-cols-4' : 'grid-cols-2'">
      <li v-for="item in items" :key="item.icon">
        <RouterLink
          :to="item.to"
          class="flex min-h-[3.5rem] flex-col items-center justify-center gap-1 text-xs text-ink-gray-5"
          exact-active-class="!text-ink-gray-9 font-medium"
        >
          <span :class="item.icon" class="size-5" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>
