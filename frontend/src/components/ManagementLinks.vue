<script setup lang="ts">
// Entry points of the management view (issue #358), drawn for reviewers only.
const links = [
  { to: { name: 'ManagementFleet' }, icon: 'lucide-truck', label: 'Fleet' },
  { to: { name: 'ManagementProjects' }, icon: 'lucide-folder-kanban', label: 'Projects' },
  { to: { name: 'ManagementCards' }, icon: 'lucide-calendar-days', label: 'Monthly cards' },
]
</script>

<template>
  <nav class="space-y-2" data-testid="management-links">
    <RouterLink
      v-for="link in links"
      :key="link.label"
      :to="link.to"
      class="flex min-h-11 items-center gap-3 rounded-xl border border-outline-gray-1 p-3"
    >
      <span :class="link.icon" class="size-5 shrink-0 text-ink-gray-5" aria-hidden="true" />
      <span class="grow">{{ __(link.label, [], 'Card Mobile') }}</span>
      <span
        class="lucide-chevron-right size-4 text-ink-gray-5 rtl:rotate-180"
        aria-hidden="true"
      />
    </RouterLink>
  </nav>
</template>
