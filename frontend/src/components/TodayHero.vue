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
import { useToast } from '@/composables/useToast';
import { showUndo } from '@/composables/useUndo';
import { formatDay, formatBetween, formatShort } from '@/utils/formatDate';

const { t, locale } = useI18n();
const reports = useReportsStore();
const periodsStore = usePeriodsStore();
const toast = useToast();
const undoWith = async (fn: () => Promise<unknown>) => { periodsStore.clearError(); await fn(); if (periodsStore.error) toast.error(periodsStore.error); };

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

const baseLength = computed(() => Math.round(ctx.value?.cycle_length || 28));
const mostLikelyIdx = computed(() => idxOf(f.value?.most_likely_start));
const r80StartIdx = computed(() => idxOf(f.value?.interval_80?.start));
const r80EndIdx = computed(() => idxOf(f.value?.interval_80?.end));

const isLate = computed(
  () => !isOngoing.value && (!!f.value?.is_late || f.value?.confidence === ('overdue' as string) || (ctx.value?.days_until_next_period ?? 1) < 0),
);
// days since the last start minus the user's usual cycle length (cycle-context cycle_length)
const daysLate = computed(() => Math.max(1, todayIdx.value - baseLength.value));

const length = computed(() => {
  if (isLate.value) return Math.max(baseLength.value, todayIdx.value) + 9;
  const last = r80EndIdx.value ?? mostLikelyIdx.value ?? baseLength.value;
  return Math.min(42, Math.max(baseLength.value, last + 1, todayIdx.value + 3, periodDays.value + 4));
});

const fertileRaw = computed(() => {
  const fw = f.value?.fertile_window ?? (ctx.value?.fertile_window?.start ? ctx.value.fertile_window : null);
  const a = idxOf(fw?.start);
  const b = idxOf(fw?.end);
  return a !== null && b !== null && b >= 0 ? { start: a, end: b } : null;
});
// a fertile window from a past cycle must never sit next to "today" in a late cycle
const fertile = computed(() => (isLate.value || isEmpty.value ? null : fertileRaw.value));
const ovulationIdx = computed(() => idxOf(f.value?.fertile_window?.ovulation_date ?? ctx.value?.ovulation_date));
const fertilePast = computed(() => !!fertile.value && fertile.value.end < todayIdx.value);

// The bubbles and the bracket must tell the same story: when the 80% range is bracketed, bubbles stay inside it
// (the thin tails outside would otherwise start before the bracket and read as a different prediction).
const forecastDays = computed(() =>
  (f.value?.days ?? [])
    .map((d) => ({ idx: idxOf(d.date) as number, p: d.p_start }))
    .filter((d) => d.idx !== null)
    .filter((d) => !bracketed.value || (d.idx >= (r80StartIdx.value as number) && d.idx <= (r80EndIdx.value as number))),
);
const bracketed = computed(() => r80StartIdx.value !== null && r80EndIdx.value !== null && r80EndIdx.value - r80StartIdx.value <= 9 && !isLate.value);
const hasForecast = computed(() => !!f.value?.interval_80 && forecastDays.value.length > 0 && !isOngoing.value);

const overdue = computed(() => (isLate.value && todayIdx.value > baseLength.value ? { start: baseLength.value, end: todayIdx.value } : null));

const rangeSpan = computed(() => {
  const r = f.value?.interval_80;
  if (!hasForecast.value || isLate.value || !r || r80StartIdx.value === null || r80EndIdx.value === null) return null;
  if (r80EndIdx.value - r80StartIdx.value > 9) return null; // too wide to bracket usefully; the hero already says "about"
  const bt = formatBetween(r.start, r.end, locale.value);
  const text = r80StartIdx.value === r80EndIdx.value ? formatShort(r.end, locale.value) : `${bt?.a}–${bt?.b}`;
  return { start: Math.max(r80StartIdx.value, todayIdx.value + 1), end: r80EndIdx.value, text };
});

// ---- words: the hero answers "when?" ----
const dateLine = computed(() => t('today.dateLine', { date: formatDay(today, locale.value) }));

// A late period can also mean a forgotten log: say so in one honest line, and when that reading is the
// likelier one the headline must not sound certain.
// A range as text, clipped to today onward: never shows a past date, null when nothing of it is left.
const clipText = (start: string, end: string): string | null => {
  if (end < todayISO) return null;
  const s = start < todayISO ? todayISO : start;
  const bt = formatBetween(s, end, locale.value);
  if (!bt) return null;
  return s === end ? formatShort(end, locale.value) : `${bt.a}–${bt.b}`;
};
const secondary = computed(() => {
  const sw = f.value?.secondary_window;
  if (!sw || isOngoing.value) return null;
  const range = clipText(sw.start, sw.end);
  if (!range) return null;
  const pct = Math.round(sw.probability * 100);
  // worded by its timing relative to the headline: an earlier window is "could also start any day now",
  // a later one is the "you may have missed logging one" reading
  const earlier = !!f.value?.most_likely_start && sw.start < f.value.most_likely_start;
  return { earlier, range, text: t('today.secondary', { range, pct }), likely: sw.probability >= 0.5 };
});
// Late: lead with lateness, then the (up to) two readings as calm lines, ranges clipped to today onward.
const lateLines = computed<string[]>(() => {
  if (!isLate.value) return [];
  const out: string[] = [];
  const sw = f.value?.secondary_window;
  const swPct = sw ? Math.round(sw.probability * 100) : null;
  if (secondary.value?.earlier && swPct !== null) {
    out.push(t('today.lateAnyDay', { range: secondary.value.range, pct: swPct }));
    const main = f.value?.interval_50 ?? f.value?.interval_80;
    const range = main ? clipText(main.start, main.end) : null;
    if (range) out.push(t('today.lateMissed', { range }));
  } else {
    if (secondary.value) out.push(secondary.value.text);
  }
  return out;
});

const hero = computed(() => {
  if (isOngoing.value) return t('today.periodDayN', { n: dayNumber.value });
  if (isLate.value) return t('today.daysLate', { count: daysLate.value }, daysLate.value);
  if (hasForecast.value && r80StartIdx.value !== null && r80EndIdx.value !== null) {
    const a = Math.max(0, r80StartIdx.value - todayIdx.value);
    const b = Math.max(0, r80EndIdx.value - todayIdx.value);
    const ml = Math.max(0, (mostLikelyIdx.value ?? r80StartIdx.value) - todayIdx.value);
    if (b === 0) return t('today.periodAnyDay');
    if (secondary.value?.likely) return t('today.periodInAbout', { n: ml });
    if (b - a > 7) return t('today.periodInAbout', { n: ml });
    if (a === b) return t('today.periodInN', { n: a }, a);
    if (a === 0) return t('today.periodWithin', { n: b });
    return t('today.periodInRange', { range: `${a}–${b}` });
  }
  return t('today.dayN', { n: dayNumber.value });
});

const sub = computed(() => {
  if (isOngoing.value) return avgPeriod.value ? t('today.periodUsually', { n: avgPeriod.value }) : null;
  if (isLate.value) return lateLines.value[0] ?? t('today.laterThanUsual');
  const bt = formatBetween(f.value?.interval_80?.start, f.value?.interval_80?.end, locale.value);
  if (hasForecast.value && bt) return t('today.between', { pct: 80, a: bt.a, b: bt.b });
  return t('today.needMore');
});
const sub2 = computed(() => {
  if (isOngoing.value) return null;
  if (isLate.value) {
    if (lateLines.value.length) return lateLines.value[1] ?? null;
    const p = f.value?.probability_next_3_days;
    return p != null ? t('today.next3', { pct: Math.round(p * 100) }) : null;
  }
  return t(`forecast.confidence.${f.value?.confidence ?? 'learning'}`);
});

defineExpose({ isLate });
const buttonText = computed(() => (isOngoing.value ? t('periodForm.endCurrent.button') : t('periodForm.recordNew.button')));
const busy = computed(() => periodsStore.loading);

// One tap, no confirmation dialog: the action happens at once and an undo toast offers to take it back.
async function act() {
  if (isEmpty.value || !isOngoing.value) {
    const p = await (isEmpty.value ? periodsStore.startPeriodToday() : periodsStore.createPeriod(todayISO));
    if (p) showUndo(t('today.undo.started'), t('today.undo.button'), () => undoWith(() => periodsStore.deletePeriod(p.id)));
    return;
  }
  if (latest.value) {
    const id = latest.value.id;
    const r = await periodsStore.updatePeriod(id, todayISO);
    if (r) showUndo(t('today.undo.ended'), t('today.undo.button'), () => undoWith(() => periodsStore.reopenPeriod(id)));
  }
}
</script>

<template>
  <section class="today phase-period" aria-labelledby="today-title">
    <CycleRing
        :length="isEmpty ? 28 : length"
        :today-idx="isEmpty ? null : todayIdx"
        :day-label="isEmpty ? '' : $t('today.dayChip', { n: dayNumber })"
        :period-days="periodDays"
        :period-expected-extra="extraDays"
        :fertile="fertile"
        :fertile-past="fertilePast"
        :ovulation-idx="fertile ? ovulationIdx : null"
        :forecast="hasForecast ? forecastDays : []"
        :range-span="rangeSpan"
        :overdue="overdue"
        :empty="isEmpty">
      <template v-if="isEmpty">
        <h1 id="today-title" class="font-display text-title leading-tight">{{ $t('today.emptyTitle') }}</h1>
        <p class="mt-2 text-sm text-ink-soft leading-snug">{{ $t('today.emptyBody') }}</p>
      </template>
      <template v-else>
        <p class="text-[0.8125rem] text-ink-soft">{{ dateLine }}</p>
        <h1 id="today-title" class="hero-line mt-2">{{ hero }}</h1>
        <p v-if="sub" class="mt-2.5 text-[0.9375rem] leading-snug text-ink text-balance">{{ sub }}</p>
        <p v-if="secondary && !isLate" class="mt-1.5 text-[0.8125rem] leading-snug text-ink-soft text-balance">{{ secondary.text }}</p>
        <p v-if="sub2" class="mt-1.5 text-[0.8125rem] leading-snug text-ink-soft text-balance">{{ sub2 }}</p>
      </template>
    </CycleRing>

    <div v-if="!isEmpty" class="legend-grid mt-3 text-xs text-ink-soft">
      <span class="inline-flex items-center gap-1.5"><span class="legend-dot" style="background: var(--color-period)"></span>{{ $t('today.legendPeriod') }}</span>
      <span v-if="!isEmpty && todayIdx > 0" class="inline-flex items-center gap-1.5"><span class="legend-elapsed"></span>{{ $t('today.legendElapsed') }}</span>
      <span v-if="fertile" class="inline-flex items-center gap-1.5"><span class="legend-bar"></span>{{ $t('today.legendFertile') }}</span>
      <span v-if="overdue" class="inline-flex items-center gap-1.5"><span class="legend-dotted"></span>{{ $t('today.legendOverdue') }}</span>
      <span v-if="fertile && ovulationIdx !== null" class="inline-flex items-center gap-1.5"><span class="legend-ov"></span>{{ $t('today.ovulation') }}</span>
      <span v-if="hasForecast" class="inline-flex items-center gap-1.5"><span class="legend-bubbles"><i></i><i></i><i></i></span>{{ $t('today.legendForecast') }}</span>
    </div>

    <div class="mt-5 px-1">
      <button @click="act" :disabled="busy" class="btn btn-primary w-full">
        {{ isEmpty ? $t('dashboard.newUser.button') : buttonText }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.hero-line {
  font-family: var(--font-display);
  font-variation-settings: "SOFT" 70, "opsz" 96;
  font-weight: 560;
  font-size: clamp(1.7rem, 8.4vw, 2.2rem);
  line-height: 1.08;
  letter-spacing: -0.02em;
  text-wrap: balance;
  color: var(--color-ink);
}
.legend-grid { display: grid; grid-template-columns: repeat(3, auto); justify-content: center; gap: .375rem 1.25rem; }
.legend-grid > span { white-space: nowrap; }
.legend-dot { display: inline-block; width: .6rem; height: .6rem; border-radius: 9999px; }
.legend-dotted { display: inline-block; width: 1.1rem; height: 0; border-top: 4px dotted var(--color-period); }
.legend-elapsed { display: inline-block; width: 1.1rem; height: .6rem; border-radius: 9999px; background: color-mix(in srgb, var(--color-period) var(--ring-tint, 20%), transparent); }
.legend-ov { display: inline-block; width: .65rem; height: .65rem; border-radius: 9999px; border: 2px solid var(--color-fertile); }
.legend-bar { display: inline-block; width: 1.1rem; height: .3rem; border-radius: 9999px; background: var(--color-fertile); }
.legend-bubbles { display: inline-flex; align-items: center; gap: 2px; }
.legend-bubbles i { display: block; border-radius: 9999px; border: 1.4px solid var(--color-period); background: color-mix(in srgb, var(--color-period) 45%, transparent); }
.legend-bubbles i:nth-child(1) { width: 5px; height: 5px; opacity: .6; }
.legend-bubbles i:nth-child(2) { width: 9px; height: 9px; }
.legend-bubbles i:nth-child(3) { width: 5px; height: 5px; opacity: .6; }
</style>
