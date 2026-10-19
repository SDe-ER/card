<script setup lang="ts">
import { ref } from 'vue'
import { Button, ErrorMessage, FormControl } from 'frappe-ui'
import { login } from '../data/session'

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await login(email.value, password.value)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
// served by Frappe (not bundled), the same file as the Desk logo
const CARD_LOGO = '/assets/card/images/card-logo.svg'
</script>

<template>
  <div class="flex min-h-dvh flex-col justify-center gap-8 p-6">
    <div class="flex flex-col items-center gap-3">
      <img :src="CARD_LOGO" alt="" class="size-16" />
      <h1 class="text-2xl font-semibold" data-testid="title">Card</h1>
    </div>
    <form class="space-y-4" @submit.prevent="submit">
      <FormControl
        v-model="email"
        type="text"
        size="lg"
        :label="__('Email', [], 'Card Mobile')"
        autocomplete="username"
        inputmode="email"
        required
      />
      <FormControl
        v-model="password"
        type="password"
        size="lg"
        :label="__('Password', [], 'Card Mobile')"
        autocomplete="current-password"
        required
      />
      <ErrorMessage :message="error" />
      <Button
        class="h-12 w-full"
        size="lg"
        variant="solid"
        type="submit"
        :loading="loading"
        :label="__('Login', [], 'Card Mobile')"
      />
    </form>
  </div>
</template>
