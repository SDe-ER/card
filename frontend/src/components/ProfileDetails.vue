<script setup lang="ts">
import { computed } from 'vue'
import type { Profile } from '../data/home'
import { __ } from '../i18n'

// The profile body (issue #357): live data of the signed-in user. Roles are the ones actually held
// (never a picker); the summary under each says what the role allows.
const props = defineProps<{ profile: Profile; online: boolean }>()

const summaries: Record<string, string> = {
  'Card Operator': __('Enter daily logs and request needs for your machines', [], 'Card Mobile'),
  'Card Supervisor': __('Review daily logs and equipment requests', [], 'Card Mobile'),
  'Card Manager': __('Approve, and see financial figures', [], 'Card Mobile'),
  'System Manager': __('Full access', [], 'Card Mobile'),
  'Card User': __('View the equipment catalog', [], 'Card Mobile'),
  'Card Reviewer': __('Review records', [], 'Card Mobile'),
}

// codes and numbers keep their left-to-right order inside a right-to-left page
const ltrKeys = ['employee-id', 'email', 'phone', 'currency', 'number-format']

const initial = computed(() => (props.profile.full_name || props.profile.user).charAt(0))

const rows = computed(
  () =>
    [
      [__('Employee ID', [], 'Card Mobile'), props.profile.employee?.name, 'employee-id'],
      [__('Designation', [], 'Card Mobile'), props.profile.employee?.designation, 'designation'],
      [__('Company', [], 'Card Mobile'), props.profile.company, 'company'],
      [__('Branch', [], 'Card Mobile'), props.profile.employee?.branch, 'branch'],
      [__('Email', [], 'Card Mobile'), props.profile.email, 'email'],
      [__('Phone', [], 'Card Mobile'), props.profile.phone, 'phone'],
      [__('Currency', [], 'Card Mobile'), props.profile.currency, 'currency'],
      [__('Number format', [], 'Card Mobile'), props.profile.number_format, 'number-format'],
    ] as [string, string | null | undefined, string][],
)
</script>

<template>
  <div class="space-y-5">
    <div class="flex items-center gap-4">
      <img
        v-if="profile.image"
        :src="profile.image"
        alt=""
        class="size-16 shrink-0 rounded-full border border-outline-gray-1 object-cover"
      />
      <span
        v-else
        class="flex size-16 shrink-0 items-center justify-center rounded-full bg-surface-gray-2 text-2xl font-semibold text-ink-gray-6"
        aria-hidden="true"
        >{{ initial }}</span
      >
      <div class="min-w-0">
        <p class="truncate text-lg font-semibold" data-testid="full-name">
          {{ profile.full_name }}
        </p>
        <p class="break-all text-sm text-ink-gray-5">{{ profile.user }}</p>
      </div>
    </div>

    <dl class="divide-y divide-outline-gray-1 rounded-xl border border-outline-gray-1">
      <template v-for="[label, value, key] in rows" :key="key">
        <div v-if="value" class="flex min-h-11 items-center justify-between gap-4 p-3">
          <dt class="shrink-0 text-sm text-ink-gray-5">{{ label }}</dt>
          <dd
            class="min-w-0 break-words text-end"
            :dir="ltrKeys.includes(key) ? 'ltr' : 'auto'"
            :data-testid="key"
          >
            {{ value }}
          </dd>
        </div>
      </template>
    </dl>

    <section class="space-y-2" data-testid="roles">
      <h2 class="text-sm font-medium text-ink-gray-5">{{ __('Roles', [], 'Card Mobile') }}</h2>
      <ul class="divide-y divide-outline-gray-1 rounded-xl border border-outline-gray-1">
        <li v-for="role in profile.roles" :key="role" class="p-3" :data-role="role">
          <p class="font-medium">{{ role }}</p>
          <p v-if="summaries[role]" class="text-sm text-ink-gray-5">{{ summaries[role] }}</p>
        </li>
      </ul>
    </section>

    <div
      class="flex min-h-11 items-center justify-between rounded-xl border border-outline-gray-1 p-3"
      data-testid="connection"
    >
      <span class="text-sm text-ink-gray-5">{{ __('Connection', [], 'Card Mobile') }}</span>
      <span class="font-medium">{{
        online ? __('Online', [], 'Card Mobile') : __('Offline', [], 'Card Mobile')
      }}</span>
    </div>
  </div>
</template>
