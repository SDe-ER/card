<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Dialog, ErrorMessage, LoadingIndicator } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import DailyLogDetail from '../components/DailyLogDetail.vue'
import { correctLog, errorText, getLog, submitLog, type DailyLog } from '../data/dailyLog'
import { getSessionContext } from '../data/session'
import { __ } from '../i18n'

// FR-150: one daily log (DailyLogDetail) and the confirmed submit or correction. The server decides:
// a refusal is shown as its message and the log is read again.
const route = useRoute()
const router = useRouter()
const log = ref<DailyLog | null>(null)
const roles = ref<string[]>([])
const error = ref('')
const busy = ref(false)
const confirming = ref<'submit' | 'correct' | null>(null)

async function load() {
  error.value = ''
  try {
    const [ctx, doc] = await Promise.all([getSessionContext(), getLog(String(route.params.name))])
    roles.value = ctx?.roles ?? []
    log.value = doc
  } catch (e) {
    error.value = errorText(e)
  }
}
load()

async function run(kind: 'submit' | 'correct') {
  if (!log.value) return
  error.value = ''
  busy.value = true
  try {
    if (kind === 'submit') {
      await submitLog(log.value)
      confirming.value = null
      router.replace({ name: 'DailyLogs', query: { submitted: '1' } })
    } else {
      const amended = await correctLog(log.value)
      confirming.value = null
      router.replace({ name: 'DailyLogEdit', params: { name: amended.name } })
    }
  } catch (e) {
    confirming.value = null
    error.value = errorText(e)
    // the stored log may have changed (e.g. cancelled but not amended): show it as it is now
    await getLog(log.value.name)
      .then((doc) => (log.value = doc))
      .catch(() => null)
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
    :busy="busy"
    :saved="!!route.query.saved"
    @submit="confirming = 'submit'"
    @correct="confirming = 'correct'"
  />
  <Dialog
    :open="confirming !== null"
    :title="confirming === 'correct' ? __('Correct this daily log') : __('Send to supervisor')"
    :message="
      confirming === 'correct'
        ? __(
            'The returned daily log is cancelled and a new draft with the same hours opens for your correction.',
          )
        : __('After sending you can no longer change the daily log.')
    "
    :actions="[
      {
        label: confirming === 'correct' ? __('Correct this daily log') : __('Send to supervisor'),
        variant: 'solid',
        loading: busy,
        onClick: () => run(confirming === 'correct' ? 'correct' : 'submit'),
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
