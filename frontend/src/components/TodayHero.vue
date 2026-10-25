<script setup lang="ts">
/**
 * The first screen: one composed view. The ring carries the state, the centre says it in words,
 * and one pill button logs the start/end of a period.
 */
import { computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { differenceInCalendarDays, parseISO, startOfDay, subDays, formatISO, isValid } from 'date-fns';
import CycleRing from '@/components/CycleRing.vue';
import { useReportsStore } from '@/stores/reports';
import { usePeriodsStore } from '@/stores/periods';
import { formatDay, formatRange } from '@/utils/formatDate';

const { t, locale } = useI18n();
const reports = useReportsStore();
const periodsStore = usePeriodsStore();

onMounted(() => {
  if (!periodsStore.periods.length) periodsStore.fetchPeriods();
});

const today = startOfDay(new Date());
const todayISO = formatISO(today, { representation: 'date' });
const idxOf = (iso: string | null | undefined): number | null => {
  if (!iso) return null;
  const d = parseISO(iso);
  return isValid(d) ? differenceInCalendarDays(d, cycleStart.value) : null;
};

const ctx = computed(() => reports.cycleContext as any);
const f = computed(() => reports.forecast);

const latest = computed(() =>
  [...periodsStore.periods].sort((a, b) => b.start_date.localeCompare(a.start_date))[0] ?? null,
);
const isOngoing = computed(() => !!latest.value && !latest.value.end_date);
const isEmpty = computed(() => !latest.value && (reports.periodStats?.count ?? 0) === 0);

const cycleStart = computed(() => {
  if (latest.value) return parseISO(latest.value.start_date);
  if (ctx.value?.cycle_day) return subDays(today, ctx.value.cycle_day - 1);
  return today;
});
const todayIdx = computed(() => differenceInCalendarDays(today, cycleStart.value));
const dayNumber = computed(() => todayIdx.value + 1);

const periodDays = computed(() => {
  if (!latest.value) return 0;
  if (isOngoing.value) return todayIdx.value + 1;
  return (idxOf(latest.value.end_date) ?? 0) + 1;
});
const avgPeriod = computed(() => Math.round(reports.periodStats?.average_duration ?? 0));
const extraDays = computed(() => (isOngoing.value ? Math.max(0, avgPeriod.value - periodDays.value) : 0));

const mostLikelyIdx = computed(() => idxOf(f.value?.most_likely_start));
const interval80EndIdx = computed(() => idxOf(f.value?.interval_80?.end));

const length = computed(() => {
  const base = interval80EndIdx.value !== null ? interval80EndIdx.value + 2 : Math.round(ctx.value?.cycle_length || 28);
  return Math.max(21, base, todayIdx.value + 3, periodDays.value + 3);
});

const fertile = computed(() => {
  const fw = f.value?.fertile_window ?? (ctx.value?.fertile_window?.start ? ctx.value.fertile_window : null);
  const a = idxOf(fw?.start);
  const b = idxOf(fw?.end);
  return a !== null && b !== null && b >= 0 ? { start: a, end: b } : null;
});
const ovulationIdx = computed(() => idxOf(f.value?.fertile_window?.ovulation_date ?? ctx.value?.ovulation_date));

const forecastDays = computed(() =>
  (f.value?.days ?? [])
    .map((d) => ({ idx: idxOf(d.date) as number, p: d.p_start }))
    .filter((d) => d.idx !== null),
);
const hasForecast = computed(() => !!f.value?.most_likely_start && forecastDays.value.length > 0 && !isOngoing.value);

const isLate = computed(() => !isOngoing.value && (!!f.value?.is_late || (ctx.value?.days_until_next_period ?? 1) < 0));
const daysLate = computed(() => {
  const n = ctx.value?.days_until_next_period;
  if (typeof n === 'number' && n < 0) return -n;
  // is_late from the forecast: measured against the usual cycle length
  return Math.max(1, dayNumber.value - Math.round(ctx.value?.cycle_length || 28));
});

const dateLabel = computed(() => t('today.eyebrow', { date: formatDay(today, locale.value) }));
const bigLine = computed(() => t('today.dayN', { n: dayNumber.value }));

const subLine = computed(() => {
  if (isOngoing.value) return avgPeriod.value ? t('today.periodUsually', { n: avgPeriod.value }) : null;
  if (isLate.value) return t('today.lateBy', { count: daysLate.value }, daysLate.value);
  const r80 = f.value?.interval_80;
  if (r80) {
    const range = formatRange(r80.start, r80.end, locale.value);
    if (range) return `${t('today.likely', { range })} · ${t('today.likelyPct', { pct: 80 })}`;
  }
  return t('today.needMore');
});
const subLine2 = computed(() => {
  if (isLate.value && f.value?.probability_next_3_days != null) {
    return t('today.next3', { pct: Math.round(f.value.probability_next_3_days * 100) });
  }
  return null;
});
const confidence = computed(() => {
  if (isOngoing.value) return null;
  const key = f.value?.confidence ?? 'learning';
  return t(`forecast.confidence.${key}`);
});

const buttonText = computed(() => (isOngoing.value ? t('periodForm.endCurrent.button') : t('periodForm.recordNew.button')));
const busy = computed(() => periodsStore.loading);

async function act() {
  if (isEmpty.value) return periodsStore.startPeriodToday();
  if (isOngoing.value && latest.value) return periodsStore.updatePeriod(latest.value.id, todayISO);
  return periodsStore.createPeriod(todayISO);
}
</script>

<template>
  <section class="today phase-period" aria-labelledby="today-title">
    <CycleRing
        :length="isEmpty ? 28 : length"
        :today-idx="isEmpty ? null : todayIdx"
        :period-days="periodDays"
        :period-expected-extra="extraDays"
        :fertile="isEmpty ? null : fertile"
        :ovulation-idx="isEmpty ? null : ovulationIdx"
        :forecast="hasForecast ? forecastDays : []"
        :most-likely-idx="hasForecast ? mostLikelyIdx : null"
        :empty="isEmpty">
      <template v-if="isEmpty">
        <h1 id="today-title" class="font-display text-title leading-tight">{{ $t('today.emptyTitle') }}</h1>
        <p class="mt-2 text-sm text-ink-soft leading-snug">{{ $t('today.emptyBody') }}</p>
      </template>
      <template v-else>
        <p class="text-[0.8125rem] text-ink-soft">{{ dateLabel }}</p>
        <h1 id="today-title" class="display-number mt-1" style="font-size: clamp(2.6rem, 14vw, 3.4rem)">{{ bigLine }}</h1>
        <p v-if="subLine" class="mt-2.5 text-[0.9375rem] leading-snug text-ink font-medium text-balance">{{ subLine }}</p>
        <p v-if="subLine2" class="mt-1 text-[0.8125rem] leading-snug text-ink-soft text-balance">{{ subLine2 }}</p>
        <p v-if="isOngoing" class="mt-2.5"><span class="phase-chip">{{ $t('today.legendPeriod') }}</span></p>
        <p v-if="confidence" class="mt-2 text-xs text-ink-soft inline-flex items-center gap-1.5">
          <span class="inline-block h-1.5 w-1.5 rounded-full bg-ink-soft/60"></span>{{ confidence }}
        </p>
      </template>
    </CycleRing>

    <div v-if="!isEmpty" class="mt-3 flex flex-wrap justify-center gap-x-5 gap-y-1.5 text-xs text-ink-soft">
      <span class="inline-flex items-center gap-1.5"><span class="legend-dot" style="background: var(--color-period)"></span>{{ $t('today.legendPeriod') }}</span>
      <span v-if="fertile" class="inline-flex items-center gap-1.5"><span class="legend-dot" style="background: var(--color-fertile); opacity: .45"></span>{{ $t('today.legendFertile') }}</span>
      <span v-if="hasForecast" class="inline-flex items-center gap-1.5"><span class="legend-fuzz"></span>{{ $t('today.legendPredicted') }}</span>
    </div>
    <p v-if="hasForecast" class="mt-2 text-center text-xs text-ink-soft max-w-[18rem] mx-auto text-balance">{{ $t('today.predictedDesc') }}</p>

    <div class="mt-5 px-1">
      <button @click="act" :disabled="busy" class="btn btn-primary w-full" :class="{ 'is-ongoing': isOngoing }">
        {{ isEmpty ? $t('dashboard.newUser.button') : buttonText }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.legend-dot { display: inline-block; width: .55rem; height: .55rem; border-radius: 9999px; }
.legend-fuzz {
  display: inline-block; width: 1.15rem; height: .55rem; border-radius: 9999px;
  background: linear-gradient(90deg, transparent, var(--color-period) 55%, transparent);
  opacity: .8;
}
</style>
