<script setup lang="ts">
/** Placeholder shapes that mirror the real layout (ring / cards / rows) instead of a spinner. */
defineProps<{ variant: 'ring' | 'card' | 'rows' | 'line'; rows?: number }>();
</script>
<template>
  <div class="sk" role="status" aria-busy="true"><span class="sr-only">{{ $t('common.loading') }}</span>
    <div v-if="variant === 'ring'" class="mx-auto flex flex-col items-center gap-5" aria-hidden="true">
      <div class="sk-ring"><i class="sk-block"></i><div class="sk-center"><i class="sk-block h-3 w-20"></i><i class="sk-block mt-3 h-8 w-36"></i><i class="sk-block mt-3 h-3 w-28"></i></div></div>
      <i class="sk-block h-12 w-full rounded-full"></i>
    </div>
    <div v-else-if="variant === 'card'" aria-hidden="true" class="sk-card"><i class="sk-block h-4 w-1/3"></i><i class="sk-block mt-4 h-9 w-2/3"></i><i class="sk-block mt-4 h-3 w-full"></i><i class="sk-block mt-2 h-3 w-4/5"></i></div>
    <div v-else-if="variant === 'rows'" aria-hidden="true" class="flex flex-col gap-3">
      <div v-for="n in rows ?? 3" :key="n" class="sk-card !p-4"><i class="sk-block h-4 w-1/2"></i><i class="sk-block mt-3 h-3 w-3/4"></i></div>
    </div>
    <i v-else class="sk-block block h-4 w-full" aria-hidden="true"></i>
  </div>
</template>
<style scoped>
.sk-block { display: block; border-radius: .75rem; background: var(--color-surface-muted); position: relative; overflow: hidden; }
.sk-block::after { content: ""; position: absolute; inset: 0; transform: translateX(-100%); background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--color-ink) 7%, transparent), transparent); }
@media (prefers-reduced-motion: no-preference) { .sk-block::after { animation: sk 1.4s ease-in-out infinite; } }
@keyframes sk { to { transform: translateX(100%); } }
.sk-ring { position: relative; width: min(100%, 24rem); aspect-ratio: 1; }
.sk-ring > .sk-block { position: absolute; inset: 0; border-radius: 9999px; background: transparent; border: 30px solid var(--color-surface-muted); }
.sk-ring > .sk-block::after { display: none; }
.sk-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.sk-card { border-radius: 1.75rem; border: 1px solid var(--color-line); background: var(--color-surface); padding: 1.5rem; }
</style>
