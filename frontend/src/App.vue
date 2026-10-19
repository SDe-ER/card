<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { FrappeUIProvider } from 'frappe-ui'
import BottomNav from './components/BottomNav.vue'

const route = useRoute()
const withNav = computed(() => !['Login', 'NoAccess', 'NotFound'].includes(String(route.name)))
</script>

<template>
  <FrappeUIProvider>
    <!-- Phone UI only: on a wide screen the same UI sits in a centered 480 px column. -->
    <div class="min-h-dvh bg-surface-gray-2">
      <div
        class="app-column relative mx-auto flex min-h-dvh w-full max-w-[480px] flex-col bg-surface-base text-ink-gray-8 shadow-sm"
      >
        <main class="flex-1" :class="withNav ? 'pb-nav' : ''">
          <RouterView />
        </main>
        <BottomNav v-if="withNav" />
      </div>
    </div>
  </FrappeUIProvider>
</template>
