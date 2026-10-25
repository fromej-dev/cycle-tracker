<template>
  <Navbar />
  <div class="container mx-auto px-4 py-8">
    <div class="max-w-md mx-auto p-8 rounded-3xl card">
      <h2 class="page-title mb-6 text-center">{{ $t('login.title') }}</h2>
      <form @submit.prevent="handleLogin">
        <div class="mb-4">
          <label for="login" class="block text-ink-soft text-sm font-medium mb-1.5">
            {{ $t('login.usernameOrEmail') }}:
          </label>
          <input
              type="text"
              id="login"
              v-model="credentials.login"
              required
              class="w-full"
          >
        </div>
        <div class="mb-6">
          <label for="password" class="block text-ink-soft text-sm font-medium mb-1.5">
            {{ $t('login.password') }}:
          </label>
          <div class="relative">
            <input
                :type="showPassword ? 'text' : 'password'"
                id="password"
                v-model="credentials.password"
                required
                class="w-full pr-10"
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
        </div>
        <div v-if="authStore.error" class="text-danger text-sm mb-4">{{ authStore.error }}</div>
        <div class="flex items-center justify-between gap-2">
          <button
              type="submit"
              :disabled="authStore.loading"
              class="btn btn-primary"
          >
            {{ authStore.loading ? $t('login.loggingIn') : $t('common.login') }}
          </button>
          <router-link :to="{ name: 'register' }" class="inline-block align-baseline font-bold text-sm text-primary hover:text-primary-hover">
            {{ $t('login.needAccount') }}
          </router-link>
        </div>
      </form>
    </div>
  </div>
    <Footer/>

</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import Navbar from "@/components/Navbar.vue";
import Footer from "@/components/Footer.vue";
import { EyeIcon, EyeSlashIcon } from '@heroicons/vue/24/outline'

const authStore = useAuthStore()

const credentials = ref<Login>({
  login: '',
  password: ''
})

const showPassword = ref(false)

const handleLogin = async () => {
  console.log(credentials.value)
  await authStore.login(credentials.value)
}
</script>

<style scoped>
/* Login specific styles */
</style>
