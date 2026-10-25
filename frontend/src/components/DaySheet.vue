<script setup lang="ts">
/** Bottom sheet for one calendar day: what we know (record vs prediction) and the two quick actions. */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { XMarkIcon } from '@heroicons/vue/24/outline';

export interface Fact { tone: 'period' | 'predicted' | 'fertile' | 'quiet'; text: string; sub?: string }
interface Props {
  title: string;
  facts: Fact[];
  canStart: boolean;
  canEnd: boolean;
  busy?: boolean;
  error?: string | null;
  startLabel: string;
  endLabel: string;
  closeLabel: string;
}
const props = defineProps<Props>();
const emit = defineEmits<{ close: []; start: []; end: [] }>();

const closeBtn = ref<HTMLButtonElement | null>(null);
const sheet = ref<HTMLElement | null>(null);
const dragY = ref(0);
let startY: number | null = null;

function onKey(e: KeyboardEvent) { if (e.key === 'Escape') emit('close'); }
onMounted(async () => {
  document.addEventListener('keydown', onKey);
  await nextTick();
  closeBtn.value?.focus({ preventScroll: true });
});
onBeforeUnmount(() => document.removeEventListener('keydown', onKey));
watch(() => props.title, () => { dragY.value = 0; });

function ts(e: TouchEvent) { startY = e.touches[0].clientY; }
function tm(e: TouchEvent) { if (startY !== null) dragY.value = Math.max(0, e.touches[0].clientY - startY); }
function te() { if (dragY.value > 80) emit('close'); dragY.value = 0; startY = null; }
const panelStyle = computed(() => (dragY.value ? { transform: `translateY(${dragY.value}px)`, transition: 'none' } : undefined));
</script>

<template>
  <div class="sheet-root">
    <div class="backdrop" @click="emit('close')"></div>
    <section ref="sheet" class="panel" role="dialog" aria-modal="true" :aria-label="title" :style="panelStyle">
      <div class="grab" @touchstart.passive="ts" @touchmove.passive="tm" @touchend="te"><span></span></div>
      <header class="flex items-start justify-between gap-3">
        <h2 class="font-display text-heading leading-tight">{{ title }}</h2>
        <button ref="closeBtn" type="button" class="close" :aria-label="closeLabel" @click="emit('close')"><XMarkIcon class="h-5 w-5" /></button>
      </header>

      <ul class="mt-3 flex flex-col gap-2.5">
        <li v-for="(f, i) in facts" :key="i" class="flex items-start gap-3">
          <span class="fact-mark" :class="`m-${f.tone}`" aria-hidden="true"></span>
          <span>
            <span class="block text-[0.9375rem] font-semibold leading-snug">{{ f.text }}</span>
            <span v-if="f.sub" class="block text-[0.8125rem] leading-snug text-ink-soft">{{ f.sub }}</span>
          </span>
        </li>
      </ul>

      <p v-if="error" class="mt-3 rounded-2xl bg-danger-soft px-3.5 py-2.5 text-[0.8125rem] leading-snug text-danger-ink" role="alert">{{ error }}</p>

      <div v-if="canStart || canEnd" class="mt-4 flex flex-col gap-2">
        <button v-if="canStart" type="button" class="btn btn-primary w-full" :disabled="busy" @click="emit('start')">{{ startLabel }}</button>
        <button v-if="canEnd" type="button" :class="['btn w-full', canStart ? 'btn-secondary' : 'btn-primary']" :disabled="busy" @click="emit('end')">{{ endLabel }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.sheet-root { position: fixed; inset: 0; z-index: 60; display: flex; align-items: flex-end; justify-content: center; }
.backdrop { position: absolute; inset: 0; background: rgb(30 15 25 / 0.42); }
.panel {
  position: relative; width: 100%; max-width: 32rem; background: var(--color-surface); color: var(--color-ink);
  border-radius: 1.75rem 1.75rem 0 0; border: 1px solid var(--color-line); border-bottom: 0;
  padding: 0.5rem 1.25rem calc(1.25rem + env(safe-area-inset-bottom));
  box-shadow: 0 -18px 40px -18px rgb(0 0 0 / 0.45);
}
.grab { display: flex; justify-content: center; padding: 0.375rem 0 0.75rem; touch-action: none; }
.grab span { width: 2.5rem; height: 0.25rem; border-radius: 9999px; background: var(--color-line-strong); }
.close { flex: none; display: grid; place-items: center; width: 2.25rem; height: 2.25rem; border-radius: 9999px; background: var(--color-surface-muted); color: var(--color-ink-soft); }
.fact-mark { flex: none; margin-top: 0.1875rem; width: 1.125rem; height: 1.125rem; border-radius: 0.4rem; }
.m-period { background: var(--color-period); }
.m-predicted { background: color-mix(in srgb, var(--color-period) 22%, var(--color-surface)); border: 1.5px dashed var(--color-period); }
.m-fertile { background: color-mix(in srgb, var(--color-fertile) 30%, var(--color-surface)); border: 1.5px solid var(--color-fertile); }
.m-quiet { background: var(--color-surface-muted); border: 1.5px solid var(--color-line-strong); }
@media (prefers-reduced-motion: no-preference) {
  .backdrop { animation: fade .2s ease-out; }
  .panel { animation: rise .26s cubic-bezier(.2,.8,.2,1); }
}
@keyframes fade { from { opacity: 0; } }
@keyframes rise { from { transform: translateY(40%); opacity: .4; } }
</style>
