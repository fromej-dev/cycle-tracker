<template>
  <nav class="bg-background text-ink border-b border-line p-4">
    <div class="container mx-auto flex justify-between items-center">
      <router-link :to="{ name: 'home' }" class="flex gap-2.5 items-center font-display text-lg text-primary">
        <img src="/assets/icons/180_tp.png" alt="Period Tracker" class="nav-image">
        {{ $t('common.title')}}
      </router-link>
      <div class="flex items-center gap-2">
          <router-link :to="{ name: 'login' }" class="px-2 py-1 rounded-lg text-sm font-medium hover:bg-surface-muted">{{ $t('common.login')}}</router-link>
          <router-link :to="{ name: 'register' }" class="px-2 py-1 rounded-lg text-sm font-medium hover:bg-surface-muted">{{ $t('common.register')}}</router-link>

        <ThemeToggle />
        <LanguagePicker/>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useAuthStore } from '@/stores/auth';
import { computed } from 'vue';
import LanguagePicker from "@/components/LanguagePicker.vue";
import ThemeToggle from "@/components/ThemeToggle.vue";

const authStore = useAuthStore();
const isAuthenticated = computed(() => authStore.isAuthenticated);

const handleLogout = () => {
  authStore.logout();
}
</script>

<style scoped>
.nav-image {
  height: 28px;
  width: 28px;
  border-radius: 25%;
}
</style>