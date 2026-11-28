<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Button, ErrorMessage } from 'frappe-ui'
import TopBar from '../components/TopBar.vue'
import InstallHint from '../components/InstallHint.vue'
import ProfileDetails from '../components/ProfileDetails.vue'
import { getProfile, setLanguage, type Profile } from '../data/home'
import { logout } from '../data/session'
import { __ } from '../i18n'

const profile = ref<Profile | null>(null)
const error = ref('')
const online = ref(typeof navigator === 'undefined' ? true : navigator.onLine)
const switching = ref(false)
// the button names the language it switches to
const toggleLabel =
  window.lang === 'ar' ? __('English', [], 'Card Mobile') : __('Arabic', [], 'Card Mobile')

const setOnline = () => (online.value = navigator.onLine)
onMounted(() => {
  window.addEventListener('online', setOnline)
  window.addEventListener('offline', setOnline)
})
onBeforeUnmount(() => {
  window.removeEventListener('online', setOnline)
  window.removeEventListener('offline', setOnline)
})

getProfile()
  .then((p) => (profile.value = p))
  .catch((e: Error) => (error.value = e.message))

// The page boot carries the language and its direction, so a switch is saved and the app reloads.
async function switchLanguage() {
  const next = window.lang === 'ar' ? 'en' : 'ar'
  switching.value = true
  error.value = ''
  try {
    await setLanguage(next)
    window.location.reload()
  } catch (e) {
    error.value = (e as Error).message
    switching.value = false
  }
}
</script>

<template>
  <TopBar :title="__('Profile', [], 'Card Mobile')" />
  <div class="space-y-5 p-4">
    <ProfileDetails v-if="profile" :profile="profile" :online="online" />
    <ErrorMessage :message="error" />

    <Button
      class="h-12 w-full"
      size="lg"
      icon-left="lucide-languages"
      :loading="switching"
      :label="toggleLabel"
      data-testid="language-toggle"
      @click="switchLanguage"
    />

    <InstallHint />

    <Button
      class="h-12 w-full"
      size="lg"
      icon-left="lucide-log-out"
      :label="__('Logout', [], 'Card Mobile')"
      @click="logout"
    />
    <p v-if="profile" class="text-center text-xs text-ink-gray-4" data-testid="version">
      {{ __('App version', [], 'Card Mobile') }} {{ profile.card_version }}
    </p>
  </div>
</template>
