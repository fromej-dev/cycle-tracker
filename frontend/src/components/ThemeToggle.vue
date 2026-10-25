<template>
  <button
    @click="toggleDark()"
    class="theme-toggle p-2 rounded-xl text-ink-soft hover:bg-surface-muted transition-colors"
    :aria-label="isDark ? $t('theme.switchToLight') : $t('theme.switchToDark')"
  >
    <MoonIcon v-if="!isDark" class="h-5 w-5" />
    <SunIcon v-else class="h-5 w-5" />
  </button>
</template>

<script setup lang="ts">
import { MoonIcon, SunIcon } from '@heroicons/vue/24/outline'
import { useDarkMode } from '@/composables/useDarkMode'

const { isDark, toggleDark } = useDarkMode()
</script>

<style scoped>
.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>
