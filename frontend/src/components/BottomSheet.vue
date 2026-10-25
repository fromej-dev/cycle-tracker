<script setup lang="ts">
/** Generic bottom sheet: forms live here on mobile (thumb reach), a centred card on wide screens. */
import { nextTick, onBeforeUnmount, onMounted, ref, computed } from 'vue';
import { XMarkIcon } from '@heroicons/vue/24/outline';

const props = defineProps<{ title: string; closeLabel: string }>();
const emit = defineEmits<{ close: [] }>();
const closeBtn = ref<HTMLButtonElement | null>(null);
const dragY = ref(0);
let startY: number | null = null;

function onKey(e: KeyboardEvent) { if (e.key === 'Escape') emit('close'); }
onMounted(async () => {
  document.addEventListener('keydown', onKey);
  document.body.style.overflow = 'hidden';
  await nextTick();
  closeBtn.value?.focus({ preventScroll: true });
});
onBeforeUnmount(() => { document.removeEventListener('keydown', onKey); document.body.style.overflow = ''; });
const ts = (e: TouchEvent) => { startY = e.touches[0].clientY; };
const tm = (e: TouchEvent) => { if (startY !== null) dragY.value = Math.max(0, e.touches[0].clientY - startY); };
const te = () => { if (dragY.value > 80) emit('close'); dragY.value = 0; startY = null; };
const panelStyle = computed(() => (dragY.value ? { transform: `translateY(${dragY.value}px)`, transition: 'none' } : undefined));
void props;
</script>

<template>
  <div class="sheet-root">
    <div class="backdrop" @click="emit('close')"></div>
    <section class="panel" role="dialog" aria-modal="true" :aria-label="title" :style="panelStyle">
      <div class="grab" @touchstart.passive="ts" @touchmove.passive="tm" @touchend="te"><span></span></div>
      <header class="flex items-start justify-between gap-3">
        <h2 class="font-display text-heading leading-tight">{{ title }}</h2>
        <button ref="closeBtn" type="button" class="close" :aria-label="closeLabel" @click="emit('close')"><XMarkIcon class="h-5 w-5" /></button>
      </header>
      <div class="mt-4"><slot /></div>
    </section>
  </div>
</template>

<style scoped>
.sheet-root { position: fixed; inset: 0; z-index: 60; display: flex; align-items: flex-end; justify-content: center; }
.backdrop { position: absolute; inset: 0; background: rgb(30 15 25 / 0.42); }
.panel {
  position: relative; width: 100%; max-width: 32rem; max-height: 92dvh; overflow-y: auto; overscroll-behavior: contain;
  background: var(--color-surface); color: var(--color-ink);
  border-radius: 1.75rem 1.75rem 0 0; border: 1px solid var(--color-line); border-bottom: 0;
  padding: 0.5rem 1.25rem calc(1.25rem + env(safe-area-inset-bottom));
  box-shadow: 0 -18px 40px -18px rgb(0 0 0 / 0.45);
}
@media (min-width: 640px) { .sheet-root { align-items: center; } .panel { border-radius: 1.75rem; border-bottom: 1px solid var(--color-line); } }
.grab { display: flex; justify-content: center; padding: 0.375rem 0 0.75rem; touch-action: none; }
.grab span { width: 2.5rem; height: 0.25rem; border-radius: 9999px; background: var(--color-line-strong); }
.close { flex: none; display: grid; place-items: center; width: 2.25rem; height: 2.25rem; border-radius: 9999px; background: var(--color-surface-muted); color: var(--color-ink-soft); }
@media (prefers-reduced-motion: no-preference) {
  .backdrop { animation: fade .2s ease-out; }
  .panel { animation: rise .26s cubic-bezier(.2,.8,.2,1); }
}
@keyframes fade { from { opacity: 0; } }
@keyframes rise { from { transform: translateY(40%); opacity: .4; } }
</style>
