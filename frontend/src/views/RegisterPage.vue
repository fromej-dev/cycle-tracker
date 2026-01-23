<template>
  <Navbar />
  <div class="container mx-auto px-4 py-8">
    <div class="max-w-md mx-auto bg-white dark:bg-gray-800 p-8 rounded-lg shadow-md">
      <h2 class="text-2xl font-bold text-primary mb-6 text-center">{{ $t('registerPage.title') }}</h2>
      <form @submit.prevent="handleRegister">
        <div class="mb-4">
          <label for="username" class="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2">
            {{ $t('registerPage.username') }}:
          </label>
          <input
              type="text"
              id="username"
              v-model="userData.username"
              required
              minlength="3"
              :class="[
                'shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 dark:text-gray-200 dark:bg-gray-800 leading-tight focus:outline-none focus:shadow-outline',
                usernameError && userData.username ? 'border-red-500 dark:border-red-400' : 'dark:border-gray-600'
              ]"
          >
          <p v-if="usernameError && userData.username" class="text-red-500 dark:text-red-400 text-xs italic mt-1">{{ usernameError }}</p>
        </div>
        <div class="mb-4">
          <label for="email" class="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2">
            {{ $t('registerPage.email') }}:
          </label>
          <input
              type="email"
              id="email"
              v-model="userData.email"
              required
              :class="[
                'shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 dark:text-gray-200 dark:bg-gray-800 leading-tight focus:outline-none focus:shadow-outline',
                emailError && userData.email ? 'border-red-500 dark:border-red-400' : 'dark:border-gray-600'
              ]"
          >
          <p v-if="emailError && userData.email" class="text-red-500 dark:text-red-400 text-xs italic mt-1">{{ emailError }}</p>
        </div>
        <div class="mb-4">
          <label for="password" class="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2">
            {{ $t('registerPage.password') }}:
          </label>
          <div class="relative">
            <input
                :type="showPassword ? 'text' : 'password'"
                id="password"
                v-model="userData.password"
                required
                :class="[
                  'shadow appearance-none border rounded w-full py-2 px-3 pr-10 text-gray-700 dark:text-gray-200 dark:bg-gray-800 leading-tight focus:outline-none focus:shadow-outline',
                  passwordError && userData.password ? 'border-red-500 dark:border-red-400' : 'dark:border-gray-600'
                ]"
            >
            <button
                type="button"
                @click="showPassword = !showPassword"
                class="absolute right-2 top-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 focus:outline-none"
                :aria-label="showPassword ? 'Hide password' : 'Show password'"
            >
              <EyeIcon v-if="!showPassword" class="h-5 w-5" />
              <EyeSlashIcon v-else class="h-5 w-5" />
            </button>
          </div>
          <p v-if="passwordError && userData.password" class="text-red-500 dark:text-red-400 text-xs italic mt-1">{{ passwordError }}</p>
        </div>
        <div class="mb-6">
          <label for="confirm_password" class="block text-gray-700 dark:text-gray-300 text-sm font-bold mb-2">
            {{ $t('registerPage.confirmPassword') }}:
          </label>
          <div class="relative">
            <input
                :type="showConfirmPassword ? 'text' : 'password'"
                id="confirm_password"
                v-model="userData.confirm_password"
                required
                :class="[
                  'shadow appearance-none border rounded w-full py-2 px-3 pr-10 text-gray-700 dark:text-gray-200 dark:bg-gray-800 leading-tight focus:outline-none focus:shadow-outline',
                  confirmPasswordError && userData.confirm_password ? 'border-red-500 dark:border-red-400' : 'dark:border-gray-600'
                ]"
            >
            <button
                type="button"
                @click="showConfirmPassword = !showConfirmPassword"
                class="absolute right-2 top-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 focus:outline-none"
                :aria-label="showConfirmPassword ? 'Hide password' : 'Show password'"
            >
              <EyeIcon v-if="!showConfirmPassword" class="h-5 w-5" />
              <EyeSlashIcon v-else class="h-5 w-5" />
            </button>
          </div>
          <p v-if="confirmPasswordError && userData.confirm_password" class="text-red-500 dark:text-red-400 text-xs italic mt-1">{{ confirmPasswordError }}</p>
        </div>
        <div v-if="authStore.error" class="text-red-500 text-sm mb-4">{{ authStore.error }}</div>
        <div class="flex items-center justify-between gap-2">
          <button
              type="submit"
              :disabled="authStore.loading || !isFormValid"
              class="bg-primary hover:bg-secondary text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ authStore.loading ? $t('registerPage.registering') : $t('common.register') }}
          </button>
          <router-link :to="{ name: 'login' }" class="inline-block align-baseline font-bold text-sm text-primary hover:text-secondary">
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
