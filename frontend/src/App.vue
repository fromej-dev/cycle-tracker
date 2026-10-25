<template>
  <pwa-install
      ref="pwa-install"
      manifest-url="/manifest.webmanifest"
      name="Period Tracker"
      description="Track your cycle and gain insights into your health."
      icon="/assets/icons/ios/512.png"/>
  <div id="app" class="h-dvh flex overflow-hidden bg-background text-ink">

    <Navigation
        :is-mobile="isMobile"
        :is-authenticated="authStore.isAuthenticated"
    />

    <div class="flex-1 flex flex-col overflow-hidden min-w-0">
      <main
          class="flex-1 overflow-y-auto bg-background"
          :class="{ 'pb-nav': isMobile && authStore.isAuthenticated }"
      >
      <RouterView />
      </main>
    </div>

  </div>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router';
import Navigation from '@/components/Navigation.vue';
import "@khmyznikov/pwa-install";
import { useTemplateRef } from "vue";
import { useDevice } from '@/composables/useDevice.js';
import { useAuthStore } from "@/stores/auth.ts";

const authStore = useAuthStore();
const { isMobile } = useDevice();
const pwaInstall = useTemplateRef('pwa-install');
</script>

<style scoped>
/* room for the fixed bottom navigation + iOS home indicator */
.pb-nav {
  padding-bottom: calc(7rem + env(safe-area-inset-bottom));
}
</style>
