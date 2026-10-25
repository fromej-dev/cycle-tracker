<script setup lang="ts">
import { undoState, runUndo } from '@/composables/useUndo';
</script>
<template>
  <Transition name="undo">
    <div v-if="undoState.action" class="undo" role="status" aria-live="polite">
      <span class="min-w-0 flex-1 text-[0.9375rem] leading-snug">{{ undoState.message }}</span>
      <button type="button" class="undo-btn" @click="runUndo">{{ undoState.label }}</button>
    </div>
  </Transition>
</template>
<style scoped>
.undo { position: fixed; z-index: 70; left: 50%; transform: translateX(-50%); bottom: calc(5.75rem + env(safe-area-inset-bottom)); width: min(calc(100% - 2rem), 26rem);
  display: flex; align-items: center; gap: .75rem; padding: .5rem .5rem .5rem 1.125rem; border-radius: 9999px;
  background: var(--color-ink); color: var(--color-background); box-shadow: 0 12px 30px -10px rgb(0 0 0 / .5); }
.undo-btn { flex: none; min-height: 2.5rem; padding: 0 1.125rem; border-radius: 9999px; font-weight: 700; background: var(--color-background); color: var(--color-ink); }
@media (prefers-reduced-motion: no-preference) { .undo-enter-active, .undo-leave-active { transition: opacity .2s, transform .2s; } .undo-enter-from, .undo-leave-to { opacity: 0; transform: translate(-50%, 12px); } }
</style>
