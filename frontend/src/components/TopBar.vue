<script setup lang="ts">
defineProps<{ title: string; back?: boolean }>()
</script>

<template>
  <header
    class="sticky top-0 z-10 flex h-14 items-center gap-2 border-b border-outline-gray-1 bg-surface-base px-4"
  >
    <button
      v-if="back"
      type="button"
      class="-ms-2 flex size-11 items-center justify-center rounded"
      :aria-label="__('Back', [], 'Card Mobile')"
      @click="$router.back()"
    >
      <span class="lucide-chevron-left size-5 rtl:rotate-180" aria-hidden="true" />
    </button>
    <h1 class="truncate text-lg font-semibold">{{ title }}</h1>
    <div class="ms-auto"><slot /></div>
  </header>
</template>
