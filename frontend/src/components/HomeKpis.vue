<script setup lang="ts">
import { formatMoney, type HomeContext } from '../data/home'

// Role-based KPI block of the home (issue #357). It draws only what the server sent: an operator
// gets no `kpis`, and `financial` arrives for a Card Manager or System Manager only.
defineProps<{ home: HomeContext }>()
</script>

<template>
  <div v-if="home.kpis" class="space-y-5" data-testid="kpis">
    <section class="grid grid-cols-3 gap-2" data-testid="fleet">
      <div class="rounded-xl border border-outline-gray-1 p-3">
        <p class="text-2xl font-semibold tabular-nums">{{ home.kpis.equipment.active }}</p>
        <p class="text-sm text-ink-gray-6">{{ __('Active', [], 'Card Mobile') }}</p>
      </div>
      <div class="rounded-xl border border-outline-gray-1 p-3">
        <p class="text-2xl font-semibold tabular-nums">{{ home.kpis.equipment.stopped }}</p>
        <p class="text-sm text-ink-gray-6">{{ __('Stopped', [], 'Card Mobile') }}</p>
      </div>
      <div class="rounded-xl border border-outline-gray-1 p-3">
        <p class="text-2xl font-semibold tabular-nums">{{ home.kpis.equipment.maintenance }}</p>
        <p class="text-sm text-ink-gray-6">{{ __('In maintenance', [], 'Card Mobile') }}</p>
      </div>
    </section>

    <section class="space-y-2" data-testid="to-review">
      <h2 class="text-sm font-medium text-ink-gray-5">{{ __('To review', [], 'Card Mobile') }}</h2>
      <div class="divide-y divide-outline-gray-1 rounded-xl border border-outline-gray-1">
        <div class="flex min-h-11 items-center justify-between p-3">
          <span>{{ __('Equipment requests', [], 'Card Mobile') }}</span>
          <span class="font-medium tabular-nums" data-testid="requests-to-review">{{
            home.kpis.requests_to_review
          }}</span>
        </div>
        <div class="flex min-h-11 items-center justify-between p-3">
          <span>{{ __('Daily logs') }}</span>
          <span class="font-medium tabular-nums" data-testid="logs-to-review">{{
            home.kpis.logs_to_review
          }}</span>
        </div>
      </div>
    </section>

    <section
      v-if="home.kpis.alerts.documents_expiring"
      class="flex min-h-11 items-center gap-3 rounded-xl border border-outline-red-1 bg-surface-red-2 p-3"
      role="alert"
      data-testid="alerts"
    >
      <span class="lucide-triangle-alert size-5 shrink-0 text-ink-red-4" aria-hidden="true" />
      <span class="grow">{{ __('Equipment documents expiring soon', [], 'Card Mobile') }}</span>
      <span class="font-semibold tabular-nums">{{ home.kpis.alerts.documents_expiring }}</span>
    </section>

    <section v-if="home.kpis.fleet_by_project.length" class="space-y-2" data-testid="by-project">
      <h2 class="text-sm font-medium text-ink-gray-5">
        {{ __('Equipment by project', [], 'Card Mobile') }}
      </h2>
      <ul class="divide-y divide-outline-gray-1 rounded-xl border border-outline-gray-1">
        <li
          v-for="row in home.kpis.fleet_by_project"
          :key="row.project ?? ''"
          class="flex min-h-11 items-center justify-between gap-3 p-3"
        >
          <span class="truncate">{{ row.project || __('No project', [], 'Card Mobile') }}</span>
          <span class="font-medium tabular-nums">{{ row.count }}</span>
        </li>
      </ul>
    </section>

    <section v-if="home.financial" class="space-y-2" data-testid="financial">
      <h2 class="text-sm font-medium text-ink-gray-5">
        {{ __('This month', [], 'Card Mobile') }}
      </h2>
      <p
        v-if="!home.financial.by_company.length"
        class="rounded-xl bg-surface-gray-1 p-3 text-ink-gray-6"
      >
        {{ __('No submitted cards this month.', [], 'Card Mobile') }}
      </p>
      <div
        v-for="row in home.financial.by_company"
        :key="row.company"
        class="divide-y divide-outline-gray-1 rounded-xl border border-outline-gray-1"
      >
        <p class="truncate p-3 text-sm text-ink-gray-5">{{ row.company }}</p>
        <div class="flex min-h-11 items-center justify-between gap-3 p-3">
          <span>{{ __('Revenue', [], 'Card Mobile') }}</span>
          <span class="font-medium tabular-nums" data-testid="revenue" dir="ltr">{{
            formatMoney(row.revenue, row.currency)
          }}</span>
        </div>
        <div class="flex min-h-11 items-center justify-between gap-3 p-3">
          <span>{{ __('Cost', [], 'Card Mobile') }}</span>
          <span class="font-medium tabular-nums" data-testid="cost" dir="ltr">{{
            formatMoney(row.cost, row.currency)
          }}</span>
        </div>
      </div>
    </section>
  </div>
</template>
