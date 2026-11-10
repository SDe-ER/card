<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Dialog, ErrorMessage, LoadingIndicator } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import DailyLogDetail from '../components/DailyLogDetail.vue'
import {
  amendmentOf,
  AmendmentExistsError,
  correctLog,
  createCorrectedDraft,
  errorText,
  getLog,
  isStale,
  submitLog,
  type DailyLog,
} from '../data/dailyLog'
import { getSessionContext } from '../data/session'
import { __ } from '../i18n'

// FR-150: one daily log (DailyLogDetail) and the confirmed submit, correction or recovery. The server
// decides: a refusal is shown as its message and the log is read again.
type Kind = 'submit' | 'correct' | 'recreate'

const route = useRoute()
const router = useRouter()
const log = ref<DailyLog | null>(null)
const amended = ref<boolean | undefined>(undefined)
const roles = ref<string[]>([])
const error = ref('')
const stale = ref(false)
const busy = ref(false)
const confirming = ref<Kind | null>(null)

// a cancelled log: does any log amend it? (decides "Create corrected draft")
async function readLog(name: string) {
  const doc = await getLog(name)
  amended.value =
    doc.docstatus === 2 ? !!(await amendmentOf(doc.name).catch(() => true)) : undefined
  log.value = doc
}

async function load() {
  error.value = ''
  stale.value = false
  try {
    const [ctx] = await Promise.all([getSessionContext(), readLog(String(route.params.name))])
    roles.value = ctx?.roles ?? []
  } catch (e) {
    error.value = errorText(e)
  }
}
load()
// the same page opens another log (e.g. the existing correction): read that one
watch(
  () => route.params.name,
  (name, previous) => name && name !== previous && load(),
)

const titles = computed<Record<Kind, string>>(() => ({
  submit: __('Send to supervisor'),
  correct: __('Correct this daily log'),
  recreate: __('Create corrected draft'),
}))
const messages = computed<Record<Kind, string>>(() => ({
  submit: __('After sending you can no longer change the daily log.'),
  correct: __(
    'The returned daily log is cancelled and a new draft with the same hours opens for your correction.',
  ),
  recreate: __('A new draft with the same hours opens for your correction.'),
}))

async function run(kind: Kind) {
  if (!log.value) return
  error.value = ''
  stale.value = false
  busy.value = true
  try {
    if (kind === 'submit') {
      await submitLog(log.value)
      confirming.value = null
      router.replace({ name: 'DailyLogs', query: { submitted: '1' } })
      return
    }
    const draft =
      kind === 'correct' ? await correctLog(log.value) : await createCorrectedDraft(log.value)
    confirming.value = null
    router.replace({ name: 'DailyLogEdit', params: { name: draft.name } })
  } catch (e) {
    confirming.value = null
    if (e instanceof AmendmentExistsError) {
      // corrected meanwhile (another tab or a retry): open the existing correction
      router.replace({ name: 'DailyLogView', params: { name: e.amendment.name } })
      return
    }
    stale.value = isStale(e)
    error.value = errorText(e)
    // the stored log may have changed (e.g. cancelled but not amended): show it as it is now
    await readLog(log.value.name).catch(() => null)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <TopBar :title="__('Daily log')" back />
  <LoadingIndicator v-if="!log && !error" class="mx-auto mt-8 size-6" />
  <ErrorMessage v-if="!log" class="m-4" :message="error" data-testid="error" />
  <DailyLogDetail
    v-else
    :log="log"
    :roles="roles"
    :error="error"
    :stale="stale"
    :busy="busy"
    :amended="amended"
    :saved="!!route.query.saved"
    @submit="confirming = 'submit'"
    @correct="confirming = 'correct'"
    @recreate="confirming = 'recreate'"
    @reload="load"
  />
  <Dialog
    :open="confirming !== null"
    :title="confirming ? titles[confirming] : ''"
    :message="confirming ? messages[confirming] : ''"
    :actions="[
      {
        label: confirming ? titles[confirming] : '',
        variant: 'solid',
        loading: busy,
        onClick: () => (confirming ? run(confirming) : undefined),
      },
      {
        label: __('Cancel', [], 'Card Mobile'),
        disabled: busy,
        onClick: () => {
          confirming = null
        },
      },
    ]"
    @update:open="(value: boolean) => !value && !busy && (confirming = null)"
  />
</template>
