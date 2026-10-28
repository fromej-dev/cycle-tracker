<script setup lang="ts">
/**
 * Every symptom for one day as tap-to-toggle chips, grouped, with the person's own usual ones first
 * and a free-text field for anything not in the list. Taps save themselves (see the symptoms store).
 */
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { CheckIcon, PlusIcon, XMarkIcon } from '@heroicons/vue/24/outline';
import { useSymptomsStore } from '@/stores/symptoms';
import { SYMPTOM_GROUPS, CUSTOM_MAX_LEN, CUSTOM_MAX_PER_DAY } from '@/utils/symptoms';
import SymptomStatus from '@/components/SymptomStatus.vue';

const props = defineProps<{ date: string }>();
const { t } = useI18n();
const store = useSymptomsStore();

const day = computed(() => store.day(props.date));
const has = (key: string) => day.value.symptoms.includes(key);

const usual = computed(() => store.suggestions.frequent.slice(0, 6));
// own symptoms used before but not picked today, ready to add again with one tap
const recentOwn = computed(() =>
  store.suggestions.recent_custom.filter((c) => !day.value.custom.some((x) => x.toLowerCase() === c.toLowerCase())).slice(0, 8),
);

const draft = ref('');
const draftError = ref<string | null>(null);
const full = computed(() => day.value.custom.length >= CUSTOM_MAX_PER_DAY);
function add() {
  const v = draft.value.trim();
  if (!v) return;
  if (v.length > CUSTOM_MAX_LEN) { draftError.value = t('symptoms.custom.tooLong', { n: CUSTOM_MAX_LEN }); return; }
  if (!store.addCustom(props.date, v)) { draftError.value = t('symptoms.custom.full', { n: CUSTOM_MAX_PER_DAY }); return; }
  draft.value = '';
  draftError.value = null;
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <section v-if="usual.length" :aria-labelledby="`usual-${date}`">
      <h3 :id="`usual-${date}`" class="eyebrow mb-2">{{ $t('symptoms.usual') }}</h3>
      <div class="chips">
        <button v-for="k in usual" :key="k" type="button" class="toggle-chip" :aria-pressed="has(k)" @click="store.toggle(date, k)">
          <CheckIcon v-if="has(k)" class="h-4 w-4" aria-hidden="true" />{{ $t(`symptoms.items.${k}`) }}
        </button>
      </div>
    </section>

    <section v-for="g in SYMPTOM_GROUPS" :key="g.key" :aria-labelledby="`g-${g.key}-${date}`">
      <h3 :id="`g-${g.key}-${date}`" class="eyebrow mb-2">{{ $t(`symptoms.groups.${g.key}`) }}</h3>
      <div class="chips">
        <button v-for="k in g.items" :key="k" type="button" class="toggle-chip" :aria-pressed="has(k)" @click="store.toggle(date, k)">
          <CheckIcon v-if="has(k)" class="h-4 w-4" aria-hidden="true" />{{ $t(`symptoms.items.${k}`) }}
        </button>
      </div>
    </section>

    <section :aria-labelledby="`own-${date}`">
      <h3 :id="`own-${date}`" class="eyebrow mb-2">{{ $t('symptoms.custom.title') }}</h3>
      <div v-if="day.custom.length || recentOwn.length" class="chips mb-3">
        <button v-for="c in day.custom" :key="`on-${c}`" type="button" class="toggle-chip" aria-pressed="true"
                :aria-label="$t('symptoms.custom.remove', { name: c })" @click="store.removeCustom(date, c)">
          {{ c }}<XMarkIcon class="h-4 w-4" aria-hidden="true" />
        </button>
        <button v-for="c in recentOwn" :key="`re-${c}`" type="button" class="toggle-chip chip-recent" aria-pressed="false"
                :disabled="full" @click="store.addCustom(date, c)">
          <PlusIcon class="h-4 w-4" aria-hidden="true" />{{ c }}
        </button>
      </div>
      <form class="flex gap-2" @submit.prevent="add">
        <label :for="`own-input-${date}`" class="sr-only">{{ $t('symptoms.custom.label') }}</label>
        <input :id="`own-input-${date}`" v-model="draft" type="text" class="min-w-0 flex-1" :maxlength="CUSTOM_MAX_LEN + 10"
               :placeholder="$t('symptoms.custom.placeholder')" enterkeyhint="done" autocomplete="off" :disabled="full"
               @input="draftError = null" />
        <button type="submit" class="add-btn" :disabled="!draft.trim() || full" :aria-label="$t('symptoms.custom.add')">
          <PlusIcon class="h-5 w-5" aria-hidden="true" />
        </button>
      </form>
      <p v-if="draftError" class="mt-1.5 text-[0.8125rem] text-danger-ink" role="alert">{{ draftError }}</p>
    </section>

    <SymptomStatus :date="date" />
  </div>
</template>

<style scoped>
.chips { display: flex; flex-wrap: wrap; gap: .5rem; }
.chip-recent { border-style: dashed; color: var(--color-ink-soft); }
.add-btn {
  flex: none; display: grid; place-items: center; width: 2.875rem; border-radius: .75rem;
  background: var(--color-primary); color: var(--color-on-primary);
}
.add-btn:disabled { background: var(--color-surface-muted); color: var(--color-ink-soft); }
</style>
