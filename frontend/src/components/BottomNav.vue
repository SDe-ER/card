<script setup lang="ts">
import { __ } from '../i18n'

const items = [
  { to: { name: 'Home' }, icon: 'lucide-house', label: __('Home', [], 'Card Mobile') },
  { to: { name: 'NewRequest' }, icon: 'lucide-circle-plus', label: __('New request') },
  { to: { name: 'Requests' }, icon: 'lucide-list-checks', label: __('My requests') },
  { to: { name: 'Profile' }, icon: 'lucide-circle-user', label: __('Profile', [], 'Card Mobile') },
]
</script>

<template>
  <nav
    class="bottom-nav fixed bottom-0 left-1/2 z-10 w-full max-w-[480px] -translate-x-1/2 border-t border-outline-gray-1 bg-surface-base"
  >
    <ul class="grid grid-cols-4">
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
