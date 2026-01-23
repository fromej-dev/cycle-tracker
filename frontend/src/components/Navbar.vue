<template>
  <nav class="bg-primary text-white p-4 shadow-md">
    <div class="container mx-auto flex justify-between items-center">
      <router-link :to="{ name: 'home' }" class="text-l flex gap-2 items-center font-bold">
        <img src="/assets/icons/180_tp.png" alt="Period Tracker" class="nav-image">
        {{ $t('common.title')}}
      </router-link>
      <div class="flex items-center gap-2">
          <router-link :to="{ name: 'login' }" class="hover:underline">{{ $t('common.login')}}</router-link>
          <router-link :to="{ name: 'register' }" class="hover:underline">{{ $t('common.register')}}</router-link>

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
  height: 27px;
  width: 27px;
  background: var(--color-background);
  border-radius: 25%;
  padding: 3px;
}
</style>