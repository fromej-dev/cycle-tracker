<template>
  <Navbar />
  <div class="container mx-auto px-4 py-8">
    <div class="max-w-md mx-auto p-8 rounded-3xl card">
      <h2 class="page-title mb-6 text-center">{{ $t('registerPage.title') }}</h2>
      <form @submit.prevent="handleRegister">
        <div class="mb-4">
          <label for="username" class="block text-ink-soft text-sm font-medium mb-1.5">
            {{ $t('registerPage.username') }}:
          </label>
          <input
              type="text"
              id="username"
              v-model="userData.username"
              required
              minlength="3"
              :class="[
                'w-full',
                usernameError && userData.username ? 'border-danger' : ''
              ]"
          >
          <p v-if="usernameError && userData.username" class="text-danger text-xs mt-1.5">{{ usernameError }}</p>
        </div>
        <div class="mb-4">
          <label for="email" class="block text-ink-soft text-sm font-medium mb-1.5">
            {{ $t('registerPage.email') }}:
          </label>
          <input
              type="email"
              id="email"
              v-model="userData.email"
              required
              :class="[
                'w-full',
                emailError && userData.email ? 'border-danger' : ''
              ]"
          >
          <p v-if="emailError && userData.email" class="text-danger text-xs mt-1.5">{{ emailError }}</p>
        </div>
        <div class="mb-4">
          <label for="password" class="block text-ink-soft text-sm font-medium mb-1.5">
            {{ $t('registerPage.password') }}:
          </label>
          <div class="relative">
            <input
                :type="showPassword ? 'text' : 'password'"
                id="password"
                v-model="userData.password"
                required
                :class="[
                  'w-full pr-10',
                  passwordError && userData.password ? 'border-danger' : ''
                ]"
            >
            <button
                type="button"
                @click="showPassword = !showPassword"
                class="absolute right-3 top-3 text-ink-soft hover:text-ink-soft focus:outline-none"
                :aria-label="showPassword ? 'Hide password' : 'Show password'"
            >
              <EyeIcon v-if="!showPassword" class="h-5 w-5" />
              <EyeSlashIcon v-else class="h-5 w-5" />
            </button>
          </div>
          <p v-if="passwordError && userData.password" class="text-danger text-xs mt-1.5">{{ passwordError }}</p>
        </div>
        <div class="mb-6">
          <label for="confirm_password" class="block text-ink-soft text-sm font-medium mb-1.5">
            {{ $t('registerPage.confirmPassword') }}:
          </label>
          <div class="relative">
            <input
                :type="showConfirmPassword ? 'text' : 'password'"
                id="confirm_password"
                v-model="userData.confirm_password"
                required
                :class="[
                  'w-full pr-10',
                  confirmPasswordError && userData.confirm_password ? 'border-danger' : ''
                ]"
            >
            <button
                type="button"
                @click="showConfirmPassword = !showConfirmPassword"
                class="absolute right-3 top-3 text-ink-soft hover:text-ink-soft focus:outline-none"
                :aria-label="showConfirmPassword ? 'Hide password' : 'Show password'"
            >
              <EyeIcon v-if="!showConfirmPassword" class="h-5 w-5" />
              <EyeSlashIcon v-else class="h-5 w-5" />
            </button>
          </div>
          <p v-if="confirmPasswordError && userData.confirm_password" class="text-danger text-xs mt-1.5">{{ confirmPasswordError }}</p>
        </div>
        <div v-if="authStore.error" class="text-danger text-sm mb-4">{{ authStore.error }}</div>
        <div class="flex items-center justify-between gap-2">
          <button
              type="submit"
              :disabled="authStore.loading || !isFormValid"
              class="btn btn-primary"
          >
            {{ authStore.loading ? $t('registerPage.registering') : $t('common.register') }}
          </button>
          <router-link :to="{ name: 'login' }" class="inline-block align-baseline font-bold text-sm text-primary hover:text-primary-hover">
            {{ $t('registerPage.alreadyHaveAccount') }}
          </router-link>
        </div>
      </form>
    </div>
  </div>
  <Footer/>
</template>

<script setup lang="ts">
import {computed, ref} from 'vue'
import { useAuthStore } from '@/stores/auth'
import Navbar from "@/components/Navbar.vue";
import Footer from "@/components/Footer.vue";
import { EyeIcon, EyeSlashIcon } from '@heroicons/vue/24/outline'

const authStore = useAuthStore()

const userData = ref<UserRegistration>({
  username: '',
  email: '',
  password: '',
  confirm_password: ''
})

const showPassword = ref(false)
const showConfirmPassword = ref(false)

// Validation computed properties
const usernameError = computed(() => {
  if (!userData.value.username) return ''
  if (userData.value.username.length < 3) return 'Username must be at least 3 characters'
  return ''
})

const emailError = computed(() => {
  if (!userData.value.email) return ''
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(userData.value.email)) return 'Please enter a valid email address'
  return ''
})

const passwordError = computed(() => {
  if (!userData.value.password) return ''
  if (userData.value.password.length < 8) return 'Password must be at least 8 characters'
  return ''
})

const confirmPasswordError = computed(() => {
  if (!userData.value.confirm_password) return ''
  if (userData.value.password !== userData.value.confirm_password) return 'Passwords do not match'
  return ''
})

const isFormValid = computed(() => {
  return userData.value.username &&
         userData.value.email &&
         userData.value.password &&
         userData.value.confirm_password &&
         !usernameError.value &&
         !emailError.value &&
         !passwordError.value &&
         !confirmPasswordError.value
})

const handleRegister = async () => {
  if (!isFormValid.value) return
  await authStore.register(userData.value)
}
</script>

<style scoped>
/* Register specific styles */
</style>
