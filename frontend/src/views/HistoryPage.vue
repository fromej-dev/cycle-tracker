<script setup lang="ts">
import CycleHistory from '@/components/CycleHistory.vue';
import { ChevronLeftIcon } from '@heroicons/vue/24/outline';
</script>
<template>
  <div class="mx-auto max-w-lg px-5 pt-7 pb-10">
    <router-link :to="{ name: 'dashboard' }" class="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-primary"><ChevronLeftIcon class="h-4 w-4" />{{ $t('nav.dashboard') }}</router-link>
    <h1 class="page-title mt-1">{{ $t('history.title') }}</h1>
    <p class="mb-5 mt-2 text-[0.9375rem] leading-snug text-ink-soft">{{ $t('history.intro') }}</p>
    <CycleHistory />
  </div>
</template>
