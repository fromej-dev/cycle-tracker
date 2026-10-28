<script setup lang="ts">
/** "How do you feel today?": the likeliest symptoms one tap away, everything else one sheet away. */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { CheckIcon, PlusIcon } from '@heroicons/vue/24/outline';
import BottomSheet from '@/components/BottomSheet.vue';
import SymptomPicker from '@/components/SymptomPicker.vue';
import SymptomStatus from '@/components/SymptomStatus.vue';
import { useSymptomsStore } from '@/stores/symptoms';
import { localToday } from '@/api/plan';
import { DEFAULT_QUICK, SYMPTOM_KEYS } from '@/utils/symptoms';

const { t } = useI18n();
const store = useSymptomsStore();
const today = localToday();
const open = ref(false);

onMounted(() => {
  store.fetchRange(today, today);
  store.fetchSuggestions();
});

const day = computed(() => store.day(today));
// what is picked today first, then the person's usual ones, topped up with common ones: 8 chips
const quick = computed(() => {
  const keys = [...new Set([...day.value.symptoms, ...store.suggestions.frequent, ...DEFAULT_QUICK])];
  return keys.filter((k) => SYMPTOM_KEYS.includes(k)).slice(0, Math.max(8, day.value.symptoms.length));
});
const has = (k: string) => day.value.symptoms.includes(k);
const total = computed(() => store.count(today));

function close() {
  open.value = false;
  store.flush(today);
}
</script>

<template>
  <section aria-labelledby="symptoms-today-heading" class="flex flex-col gap-3">
    <div>
      <h2 id="symptoms-today-heading" class="section-title">{{ $t('symptoms.today.title') }}</h2>
      <p class="mt-1 text-[0.9375rem] leading-snug text-ink-soft">{{ $t('symptoms.today.hint') }}</p>
    </div>
    <div class="flex flex-wrap gap-2">
      <button v-for="k in quick" :key="k" type="button" class="toggle-chip" :aria-pressed="has(k)" @click="store.toggle(today, k)">
        <CheckIcon v-if="has(k)" class="h-4 w-4" aria-hidden="true" />{{ $t(`symptoms.items.${k}`) }}
      </button>
      <button v-for="c in day.custom" :key="`c-${c}`" type="button" class="toggle-chip" aria-pressed="true"
              :aria-label="$t('symptoms.custom.remove', { name: c })" @click="store.removeCustom(today, c)">
        <CheckIcon class="h-4 w-4" aria-hidden="true" />{{ c }}
      </button>
      <button type="button" class="toggle-chip more" @click="open = true">
        <PlusIcon class="h-4 w-4" aria-hidden="true" />{{ $t('symptoms.today.more') }}
      </button>
    </div>
    <SymptomStatus :date="today" />

    <BottomSheet v-if="open" :title="total ? t('symptoms.today.sheetTitleN', { n: total }, total) : t('symptoms.today.sheetTitle')"
                 :close-label="$t('calendar.close')" @close="close">
      <SymptomPicker :date="today" />
      <button type="button" class="btn btn-primary mt-4 w-full" @click="close">{{ $t('symptoms.done') }}</button>
    </BottomSheet>
  </section>
</template>

<style scoped>
.more { border-style: dashed; color: var(--color-primary); font-weight: 600; }
</style>
