<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, FormControl, LoadingIndicator, TextInput } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import DailyLogRowFields from '../components/DailyLogRowFields.vue'
import {
  createLog,
  draftFrom,
  errorText,
  getLog,
  invalidRows,
  machinesOn,
  newRow,
  projectOptions,
  stopReasons,
  today,
  updateLog,
  type DailyLog,
  type DraftLog,
  type LogMachine,
  type StopReason,
} from '../data/dailyLog'
import { getPortal } from '../data/needs'
import { getSessionContext } from '../data/session'
import { __ } from '../i18n'

// FR-150: create a daily log, or edit a draft one. Only the operator's entries are sent; the
// server checks the company, the project, each equipment's assignment that day and the hours.
const route = useRoute()
const router = useRouter()
const editing = computed(() => route.name === 'DailyLogEdit')

const loaded = ref(false)
const error = ref('')
const saving = ref(false)
const company = ref('')
const machines = ref<LogMachine[]>([])
const reasons = ref<StopReason[] | null>(null)
const stored = ref<DailyLog | null>(null)
const draft = ref<DraftLog>({ project: '', log_date: today(), notes: '', rows: [] })
const adding = ref('')

const locked = computed(() => !!stored.value && stored.value.docstatus !== 0)

async function load() {
  error.value = ''
  try {
    const [ctx, portal] = await Promise.all([getSessionContext(), getPortal()])
    machines.value = portal.machines
    if (editing.value) {
      stored.value = await getLog(String(route.params.name))
      company.value = stored.value.company
      draft.value = draftFrom(stored.value)
    } else {
      company.value = ctx?.employee?.company || ''
      const projects = projectOptions(portal.machines)
      if (projects.length === 1) draft.value.project = projects[0].value
    }
    reasons.value = company.value ? await stopReasons(company.value).catch(() => null) : null
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loaded.value = true
  }
}
load()

// a new log lists every machine of the chosen project; the operator removes the ones that did not work
watch(
  () => draft.value.project,
  (project, previous) => {
    if (editing.value || project === previous) return
    draft.value.rows = project ? machinesOn(project, machines.value).map(newRow) : []
  },
)

const projects = computed(() => projectOptions(machines.value, stored.value?.project))
const addable = computed(() => {
  const listed = new Set(draft.value.rows.map((r) => r.equipment))
  return machinesOn(draft.value.project, machines.value)
    .filter((m) => !listed.has(m.name))
    .map((m) => ({ label: m.equipment_name || m.name, value: m.name }))
})

function addMachine() {
  const machine = machines.value.find((m) => m.name === adding.value)
  if (machine) draft.value.rows.push(newRow(machine))
  adding.value = ''
}

function rowLabel(i: number) {
  const row = draft.value.rows[i]
  return row.equipment_name || row.equipment
}

async function save() {
  error.value = ''
  if (!company.value) {
    error.value = __('Your account is not linked to an employee of a company.')
    return
  }
  if (!draft.value.project || !draft.value.log_date) {
    error.value = __('Choose the project and the date.')
    return
  }
  if (!draft.value.rows.length) {
    error.value = __('Add at least one equipment row to the daily log.')
    return
  }
  const invalid = invalidRows(draft.value.rows)
  if (invalid.length) {
    error.value = __('Row {0}: hours cannot be negative or exceed 24 hours together.', [
      invalid.join(', '),
    ])
    return
  }
  saving.value = true
  try {
    const saved = stored.value
      ? await updateLog(stored.value, draft.value)
      : await createLog(company.value, draft.value)
    router.replace({ name: 'DailyLogView', params: { name: saved.name }, query: { saved: '1' } })
  } catch (e) {
    error.value = errorText(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <TopBar :title="editing ? __('Edit daily log') : __('New daily log')" back />
  <LoadingIndicator v-if="!loaded" class="mx-auto mt-8 size-6" />
  <template v-else>
    <div v-if="locked" class="m-4 space-y-3 rounded-lg bg-surface-gray-1 p-4 text-ink-gray-6">
      <p>{{ __('This daily log was sent to the supervisor; it can no longer be edited.') }}</p>
      <Button
        :label="__('View daily log')"
        :route="{ name: 'DailyLogView', params: { name: stored?.name } }"
      />
    </div>
    <ErrorMessage
      v-else-if="!editing && !stored && error && !machines.length"
      class="m-4"
      :message="error"
    />
    <p
      v-else-if="!editing && !machines.length"
      class="m-4 rounded-lg bg-surface-gray-1 p-4 text-ink-gray-6"
    >
      {{ __('No equipment is assigned to you this month.') }}
    </p>
    <ErrorMessage v-else-if="editing && !stored" class="m-4" :message="error" />
    <form v-else class="space-y-5 p-4" autocomplete="off" @submit.prevent="save">
      <div class="space-y-1.5">
        <label for="log-date" class="block text-xs text-ink-gray-5">{{
          __('Daily log date')
        }}</label>
        <TextInput
          id="log-date"
          v-model="draft.log_date"
          type="date"
          size="lg"
          :max="today()"
          required
          data-testid="log-date"
        />
      </div>
      <FormControl
        v-model="draft.project"
        type="select"
        size="lg"
        :label="__('Project', [], 'Card Mobile')"
        :options="projects"
        :placeholder="__('Project', [], 'Card Mobile')"
        :disabled="editing"
        required
      />

      <DailyLogRowFields
        v-for="(row, i) in draft.rows"
        :key="row.name || row.equipment"
        v-model="draft.rows[i]"
        :index="i"
        :label="rowLabel(i)"
        :reasons="reasons"
        :removable="draft.rows.length > 1"
        @remove="draft.rows.splice(i, 1)"
      />

      <div v-if="addable.length" class="flex items-end gap-2">
        <FormControl
          v-model="adding"
          class="flex-1"
          type="select"
          size="lg"
          :label="__('Add equipment')"
          :options="addable"
          :placeholder="__('Equipment', [], 'Card Mobile')"
        />
        <Button
          class="h-10"
          size="lg"
          icon-left="lucide-plus"
          :disabled="!adding"
          :label="__('Add', [], 'Card Mobile')"
          @click="addMachine"
        />
      </div>

      <FormControl
        v-model="draft.notes"
        type="textarea"
        :label="__('Notes', [], 'Card Mobile')"
        :rows="2"
        maxlength="1000"
      />

      <ErrorMessage :message="error" data-testid="error" />
      <Button
        class="h-12 w-full"
        size="lg"
        variant="solid"
        type="submit"
        :loading="saving"
        :label="__('Save draft')"
      />
    </form>
  </template>
</template>
