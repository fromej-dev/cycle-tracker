<script setup lang="ts">
/** A date input that shows the date in the app's own locale ("4 Nov 2026") and opens the native picker. */
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { CalendarDaysIcon } from '@heroicons/vue/24/outline';
import { parseISO, isValid, format } from 'date-fns';
import { dfLocale } from '@/utils/formatDate';

const props = defineProps<{ modelValue: string; id: string; min?: string; max?: string; label: string }>();
const emit = defineEmits<{ 'update:modelValue': [v: string]; change: [] }>();
const { locale } = useI18n();
const input = ref<HTMLInputElement | null>(null);
const text = computed(() => {
  const d = props.modelValue ? parseISO(props.modelValue) : null;
  return d && isValid(d) ? format(d, 'd MMM yyyy', { locale: dfLocale(locale.value) }).replace(/\./g, '') : '';
});
function open() { try { input.value?.showPicker?.(); } catch { /* the transparent input still takes the tap */ } }
</script>
<template>
  <div class="df">
    <span class="df-text" :class="{ empty: !text }" aria-hidden="true">{{ text || '—' }}</span>
    <CalendarDaysIcon class="df-icon" aria-hidden="true" />
    <input :id="id" ref="input" type="date" class="df-input" :value="modelValue" :min="min" :max="max" :aria-label="`${label}: ${text}`"
           @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)" @change="emit('change')" @click="open" />
  </div>
</template>
<style scoped>
.df { position: relative; display: flex; align-items: center; min-height: 3rem; border: 1px solid var(--color-line-strong); border-radius: .75rem; background: var(--color-input); padding: 0 .875rem; }
.df:focus-within { border-color: var(--color-primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 22%, transparent); }
.df-text { flex: 1; min-width: 0; font-weight: 500; white-space: nowrap; }
.df-icon { flex: none; width: 1.25rem; height: 1.25rem; color: var(--color-primary); }
.df-input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; border: 0; padding: 0; cursor: pointer; }
</style>
