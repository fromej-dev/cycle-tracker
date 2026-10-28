<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  addDays, addMonths, differenceInCalendarDays, endOfMonth, format, formatISO, isSameMonth, parseISO,
  startOfDay, startOfMonth, startOfWeek, subDays,
} from 'date-fns';
import { ChevronLeftIcon, ChevronRightIcon, PencilSquareIcon, PlusIcon } from '@heroicons/vue/24/outline';
import CalendarDay from '@/components/CalendarDay.vue';
import DaySheet, { type Fact } from '@/components/DaySheet.vue';
import BottomSheet from '@/components/BottomSheet.vue';
import SymptomPicker from '@/components/SymptomPicker.vue';
import { useSymptomsStore } from '@/stores/symptoms';
import { usePeriodsStore } from '@/stores/periods';
import { useReportsStore } from '@/stores/reports';
import { dateCheckApi } from '@/api/plan';
import { useCalendarForecast, setExternalDays, clearExternalDays } from '@/composables/useCalendarForecast';
import { dfLocale, formatDay, formatBetween } from '@/utils/formatDate';

const { t, locale } = useI18n();
const periodsStore = usePeriodsStore();
const reports = useReportsStore();
const symptoms = useSymptomsStore();
const { forecast, forecastEnd, reason, byDate, prob, fertileMap, lastCovered } = useCalendarForecast();

const iso = (d: Date) => formatISO(d, { representation: 'date' });
const today = startOfDay(new Date());
const todayISO = iso(today);

onMounted(() => {
  periodsStore.fetchPeriods(1, 100);
  reports.fetchForecast();
  if (!(reports.cycleContext as any)?.cycle_length) reports.fetchCycleContext();
});

// ---- month navigation ----
const month = ref(startOfMonth(today));
const dir = ref<'next' | 'prev'>('next');
const MAX_AHEAD = 12;
const canNext = computed(() => differenceInCalendarDays(month.value, startOfMonth(today)) < MAX_AHEAD * 28);
const canPrev = computed(() => month.value > startOfMonth(new Date(2000, 0, 1)));
const isCurrent = computed(() => isSameMonth(month.value, today));
function go(delta: number) {
  if ((delta > 0 && !canNext.value) || (delta < 0 && !canPrev.value)) return;
  dir.value = delta > 0 ? 'next' : 'prev';
  month.value = addMonths(month.value, delta);
}
function goToday() {
  dir.value = month.value > today ? 'prev' : 'next';
  month.value = startOfMonth(today);
}
let sx = 0, sy = 0;
const swipeStart = (e: TouchEvent) => { sx = e.touches[0].clientX; sy = e.touches[0].clientY; };
const swipeEnd = (e: TouchEvent) => {
  const dx = e.changedTouches[0].clientX - sx;
  const dy = e.changedTouches[0].clientY - sy;
  if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) go(dx < 0 ? 1 : -1);
};

// ---- locale-aware grid ----
const loc = computed(() => dfLocale(locale.value));
const weekStartsOn = computed(() => (loc.value.options?.weekStartsOn ?? 0) as 0 | 1 | 2 | 3 | 4 | 5 | 6);
const weekdays = computed(() => {
  const s = startOfWeek(today, { weekStartsOn: weekStartsOn.value });
  return Array.from({ length: 7 }, (_, i) => format(addDays(s, i), 'EEEEEE', { locale: loc.value }).replace('.', ''));
});
const monthTitle = computed(() => format(month.value, 'LLLL yyyy', { locale: loc.value }));

// ---- records ----
interface Logged { id: number; start: string; end: string | null; day: number; first: boolean; last: boolean }
const loggedMap = computed(() => {
  const m = new Map<string, Logged>();
  for (const p of periodsStore.periods) {
    const s = parseISO(p.start_date);
    const e = p.end_date ? parseISO(p.end_date) : today > s ? today : s;
    const n = differenceInCalendarDays(e, s);
    for (let i = 0; i <= Math.min(n, 60); i++) {
      m.set(iso(addDays(s, i)), { id: p.id, start: p.start_date, end: p.end_date, day: i + 1, first: i === 0, last: i === n });
    }
  }
  return m;
});

interface Cell { iso: string; day: number; blank: boolean; col: number }
const monthCells = (m: Date): Cell[] => {
  const first = startOfMonth(m);
  const lead = (first.getDay() - weekStartsOn.value + 7) % 7;
  const n = endOfMonth(m).getDate();
  const out: Cell[] = [];
  for (let i = 0; i < lead; i++) out.push({ iso: '', day: 0, blank: true, col: i % 7 });
  for (let d = 1; d <= n; d++) out.push({ iso: iso(addDays(first, d - 1)), day: d, blank: false, col: (lead + d - 1) % 7 });
  return out;
};
// the chosen month plus a peek at the next one, so a forecast that crosses the month end is visible at once
const months = computed(() => [month.value, addMonths(month.value, 1)].map((m) => ({
  key: m.getTime(),
  title: format(m, 'LLLL yyyy', { locale: loc.value }),
  cells: monthCells(m),
})));

const startWinSet = computed(() => {
  const r = forecast.value?.interval_80;
  const set = new Set<string>();
  if (reason.value || !r) return set;
  for (let d = parseISO(r.start); d <= parseISO(r.end); d = addDays(d, 1)) set.add(iso(d));
  return set;
});
const startWinOf = (c: Cell) => {
  if (!startWinSet.value.has(c.iso) || loggedMap.value.get(c.iso)) return null;
  const prev = c.col > 0 && startWinSet.value.has(iso(subDays(parseISO(c.iso), 1)));
  const next = c.col < 6 && startWinSet.value.has(iso(addDays(parseISO(c.iso), 1)));
  return prev && next ? 'mid' : prev ? 'last' : next ? 'first' : 'only';
};
const info = (c: Cell) => {
  const lg = loggedMap.value.get(c.iso);
  const pr = lg ? null : prob(c.iso);
  return {
    logged: !!lg,
    joinPrev: !!lg && c.col > 0 && !!loggedMap.value.get(iso(subDays(parseISO(c.iso), 1))),
    joinNext: !!lg && c.col < 6 && !!loggedMap.value.get(iso(addDays(parseISO(c.iso), 1))),
    // every day of the underlined start window shows at least the faintest predicted shade
    pBleeding: lg ? 0 : startWinSet.value.has(c.iso) && !reason.value ? Math.max(pr?.p_bleeding ?? 0, 0.19) : pr?.p_bleeding ?? 0,
    fertile: !lg ? fertileMap.value.get(c.iso)?.strength ?? 0 : 0,
    projected: fertileMap.value.get(c.iso)?.projected ?? false,
    ovulation: !lg && !!fertileMap.value.get(c.iso)?.ovulation,
    far: !!forecastEnd.value && c.iso > forecastEnd.value,
    startWin: startWinOf(c),
    likelyStart: !lg && forecast.value?.most_likely_start === c.iso && !reason.value,
    noted: symptoms.count(c.iso) > 0,
  };
};

// ---- explanation line under the header ----
const summary = computed(() => {
  if (reason.value === 'late') return t('calendar.noteLate');
  if (reason.value === 'learning') return t('calendar.noteLearning');
  const r = forecast.value?.interval_80;
  const bt = formatBetween(r?.start, r?.end, locale.value);
  if (bt) {
    const span = r!.start === r!.end ? bt.b : `${bt.a}–${bt.b}`;
    return t('calendar.noteForecast', { range: span, pct: 80 });
  }
  return null;
});
const shownEnd = computed(() => endOfMonth(addMonths(month.value, 1)));
// Months past the ~45-day forecast: fetch Date Check in <=60-day chunks (cached) so far months are shaded too.
const MAX_DAYS = 366;
const fetched = new Set<string>();
async function loadFar() {
  const fe = forecastEnd.value;
  if (reason.value || !fe) return;
  const first = addDays(parseISO(fe), 1);
  const limit = addDays(today, MAX_DAYS);
  const want = shownEnd.value < limit ? shownEnd.value : limit;
  for (let s = first; s <= want; s = addDays(s, 60)) {
    const e = addDays(s, 59) > limit ? limit : addDays(s, 59);
    if (e < startOfMonth(month.value) || s > shownEnd.value) continue;
    const key = `${iso(s)}`;
    if (fetched.has(key)) continue;
    fetched.add(key);
    try {
      const r = await dateCheckApi.check(iso(s), iso(e));
      if (r.data.status === 'ok') setExternalDays(r.data.days);
    } catch { fetched.delete(key); }
  }
}
watch([month, forecastEnd], loadFar);
watch(forecast, (n, o) => { if (o && n !== o) { fetched.clear(); clearExternalDays(); loadFar(); } });
onMounted(loadFar);

// symptoms for the shown months (never the future: nothing can be noted there yet)
function loadSymptoms() {
  const start = startOfMonth(month.value);
  if (start > today) return;
  const end = shownEnd.value < today ? shownEnd.value : today;
  symptoms.fetchRange(iso(start), iso(end));
}
watch(month, loadSymptoms);
onMounted(() => { loadSymptoms(); symptoms.fetchSuggestions(); });

const beyond = computed(() => !reason.value && !!forecastEnd.value && shownEnd.value > parseISO(forecastEnd.value) && startOfMonth(month.value) <= addDays(today, MAX_DAYS));
const beyondAll = computed(() => !reason.value && !!forecastEnd.value && startOfMonth(month.value) > addDays(today, MAX_DAYS));
const hasNoted = computed(() => Object.values(symptoms.byDate).some((d) => d.symptoms.length + d.custom.length > 0));
const hasFertile = computed(() => fertileMap.value.size > 0);
const hasPred = computed(() => !reason.value && [...byDate.value.values()].some((v) => v.p_bleeding >= 0.18));

// ---- sheet ----
const selected = ref<string | null>(null);
const busy = ref(false);
const error = ref<string | null>(null);
const pct = (p: number) => (p < 0.01 ? '<1' : p > 0.99 ? '99+' : String(Math.round(p * 100)));

function open(c: Cell) {
  if (c.blank) return;
  error.value = null;
  selected.value = c.iso;
}
const selDate = computed(() => (selected.value ? parseISO(selected.value) : null));
const sheetTitle = computed(() => (selected.value ? formatDay(selected.value, locale.value, true) ?? '' : ''));
const isFutureSel = computed(() => !!selected.value && selected.value > todayISO);

const facts = computed<Fact[]>(() => {
  const s = selected.value;
  if (!s) return [];
  const out: Fact[] = [];
  const lg = loggedMap.value.get(s);
  const pr = prob(s);
  if (lg) {
    out.push({ tone: 'period', text: t('calendar.facts.logged', { n: lg.day }), sub: lg.end ? undefined : lg.last ? t('calendar.facts.ongoing') : undefined });
  } else if (pr && pr.p_bleeding >= 0.18) {
    out.push({ tone: 'predicted', text: t('calendar.facts.chance', { pct: pct(pr.p_bleeding) }), sub: forecast.value?.most_likely_start === s ? t('calendar.facts.likelyStart') : t('calendar.facts.predictionNote') });
  }
  const fd = !lg ? fertileMap.value.get(s) : undefined;
  if (fd?.ovulation) {
    const oi = fd.projected ? null : forecast.value?.fertile_window?.ovulation_interval_80;
    const bt = formatBetween(oi?.start, oi?.end, locale.value);
    out.push({ tone: 'fertile', text: t('calendar.facts.ovulation'), sub: bt ? t('calendar.facts.ovulationRange', { a: bt.a, b: bt.b }) : fd.projected ? t('calendar.facts.projected') : undefined });
  } else if (fd) {
    out.push({ tone: 'fertile', text: t('calendar.facts.fertile'), sub: fd.projected ? t('calendar.facts.projected') : undefined });
  }
  if (!out.length) {
    if (reason.value === 'late') out.push({ tone: 'quiet', text: t('calendar.facts.late') });
    else if (reason.value === 'learning') out.push({ tone: 'quiet', text: t('calendar.facts.learning') });
    else if (s < todayISO) out.push({ tone: 'quiet', text: t('calendar.facts.nothingLogged') });
    else if (lastCovered.value && s > lastCovered.value) out.push({ tone: 'quiet', text: t('calendar.facts.tooFar') });
    else out.push({ tone: 'quiet', text: t('calendar.facts.noPeriod') });
  }
  return out;
});

// the period (if any) whose span contains the day, or the open one that began before it
const openBefore = computed(() => {
  const s = selected.value;
  if (!s) return null;
  return periodsStore.periods.find((p) => !p.end_date && p.start_date <= s) ?? null;
});
const containing = computed(() => (selected.value ? loggedMap.value.get(selected.value) ?? null : null));
const canStart = computed(() => !!selected.value && !isFutureSel.value && !containing.value && !(openBefore.value && openBefore.value.start_date < selected.value));
const canEnd = computed(() => {
  const s = selected.value;
  if (!s || isFutureSel.value) return false;
  const c = containing.value;
  if (c) return c.end !== s;
  return !!openBefore.value;
});

function friendly(): string {
  const raw = periodsStore.error;
  return raw ? `${t('calendar.errors.generic')} (${raw})` : t('calendar.errors.generic');
}
async function startHere() {
  if (!selected.value) return;
  busy.value = true; error.value = null;
  periodsStore.clearError();
  const r = await periodsStore.createPeriod(selected.value);
  busy.value = false;
  if (!r) error.value = friendly(); else selected.value = null;
}
async function endHere() {
  if (!selected.value) return;
  const id = containing.value?.id ?? openBefore.value?.id;
  if (id === undefined) return;
  busy.value = true; error.value = null;
  periodsStore.clearError();
  const r = await periodsStore.updatePeriod(id, selected.value);
  busy.value = false;
  if (!r) error.value = friendly(); else selected.value = null;
}

// ---- symptoms of the selected day ----
const selSymptoms = computed(() => {
  if (!selected.value) return [];
  const d = symptoms.day(selected.value);
  return [...d.symptoms.map((k) => t(`symptoms.items.${k}`)), ...d.custom];
});
const symptomsFor = ref<string | null>(null);
const symptomsTitle = computed(() => (symptomsFor.value ? t('symptoms.calendar.sheetTitle', { date: formatDay(symptomsFor.value, locale.value, true) ?? '' }) : ''));
function editSymptoms() {
  symptomsFor.value = selected.value;
  selected.value = null;
}
function closeSymptoms() {
  const d = symptomsFor.value;
  symptomsFor.value = null;
  if (d) symptoms.flush(d);
}

const dayLabel = (c: Cell) => {
  const lg = loggedMap.value.get(c.iso);
  const pr = lg ? null : prob(c.iso);
  const n = symptoms.count(c.iso);
  const base = (formatDay(c.iso, locale.value, true) ?? '') + (n ? `, ${t('symptoms.calendar.count', { n }, n)}` : '');
  if (lg) return `${base}, ${t('calendar.facts.logged', { n: lg.day })}`;
  if (pr && pr.p_bleeding >= 0.18) return `${base}, ${t('calendar.facts.chance', { pct: pct(pr.p_bleeding) })}`;
  if (fertileMap.value.get(c.iso)) return `${base}, ${t('calendar.facts.fertile')}`;
  return base;
};
</script>

<template>
  <div class="mx-auto max-w-lg px-3 pt-5 pb-28">
    <header class="flex items-center justify-between px-1">
      <button type="button" class="nav-btn" :aria-label="$t('calendar.prev')" :disabled="!canPrev" @click="go(-1)"><ChevronLeftIcon class="h-5 w-5" /></button>
      <div class="text-center">
        <h1 class="font-display text-title capitalize leading-none" aria-live="polite">{{ monthTitle }}</h1>
      </div>
      <button type="button" class="nav-btn" :aria-label="$t('calendar.next')" :disabled="!canNext" @click="go(1)"><ChevronRightIcon class="h-5 w-5" /></button>
    </header>

    <div class="mt-2 flex min-h-8 items-start justify-between gap-3 px-1">
      <p class="text-[0.8125rem] leading-snug text-ink-soft text-pretty">{{ summary }}</p>
      <button v-if="!isCurrent" type="button" class="today-btn" @click="goToday">{{ $t('calendar.today') }}</button>
    </div>

    <div class="mt-3 grid grid-cols-7 border-b border-line pb-1.5" aria-hidden="true">
      <span v-for="(w, i) in weekdays" :key="i" class="eyebrow text-center !text-[0.6875rem]">{{ w }}</span>
    </div>

    <div class="grid-wrap" @touchstart.passive="swipeStart" @touchend.passive="swipeEnd">
      <Transition :name="`slide-${dir}`" mode="out-in">
        <div :key="month.getTime()">
          <section v-for="(m, mi) in months" :key="m.key" :class="mi ? 'mt-3' : ''" :aria-label="m.title">
            <h2 v-if="mi" class="month-label capitalize">{{ m.title }}</h2>
            <div class="grid grid-cols-7" role="grid" :aria-label="m.title">
              <template v-for="(c, i) in m.cells" :key="i">
                <span v-if="c.blank" aria-hidden="true"></span>
                <CalendarDay v-else
                    :day="c.day"
                    v-bind="info(c)"
                    :today="c.iso === todayISO"
                    :selected="c.iso === selected"
                    :label="dayLabel(c)"
                    @click="open(c)" />
              </template>
            </div>
          </section>
        </div>
      </Transition>
    </div>

    <p v-if="beyondAll" class="mt-2 px-1 text-[0.8125rem] leading-snug text-ink-soft">{{ $t('calendar.noteBeyond') }}</p>
    <p v-else-if="beyond" class="mt-2 px-1 text-[0.8125rem] leading-snug text-ink-soft">{{ $t('calendar.notePartial') }}</p>

    <ul class="legend mt-4 border-t border-line pt-3.5" :aria-label="$t('calendar.legend.title')">
      <li><span class="sw sw-logged"></span>{{ $t('calendar.legend.logged') }}</li>
      <li v-if="hasPred"><span class="sw-scale"><i class="sw sw-pred" style="--s:.15"></i><i class="sw sw-pred" style="--s:.5"></i><i class="sw sw-pred" style="--s:1"></i></span>{{ $t('calendar.legend.predicted') }}</li>
      <li v-if="hasFertile"><span class="sw sw-fertile"></span>{{ $t('calendar.legend.fertile') }}</li>
      <li v-if="hasFertile"><span class="sw-ov"></span>{{ $t('calendar.legend.ovulation') }}</li>
      <li v-if="hasPred"><span class="sw-win"></span>{{ $t('calendar.legend.window') }}</li>
      <li v-if="hasPred"><span class="sw-start"></span>{{ $t('calendar.legend.start') }}</li>
      <li v-if="hasNoted"><span class="sw-noted"></span>{{ $t('calendar.legend.symptoms') }}</li>
      <li><span class="sw sw-today"></span>{{ $t('calendar.legend.today') }}</li>
    </ul>
    <p v-if="hasPred" class="mt-2 text-[0.75rem] leading-snug text-ink-soft">{{ $t('calendar.legend.hint') }}</p>

    <DaySheet v-if="selected"
        :title="sheetTitle"
        :facts="facts"
        :can-start="canStart"
        :can-end="canEnd"
        :busy="busy"
        :error="error"
        :start-label="$t('calendar.start')"
        :end-label="$t('calendar.end')"
        :close-label="$t('calendar.close')"
        @close="selected = null"
        @start="startHere"
        @end="endHere">
      <div v-if="!isFutureSel" class="mt-4 border-t border-line pt-3.5">
        <p class="eyebrow">{{ $t('symptoms.calendar.title') }}</p>
        <p v-if="selSymptoms.length" class="mt-1.5 text-[0.9375rem] leading-snug">{{ selSymptoms.join(', ') }}</p>
        <button type="button" class="sym-btn mt-2" @click="editSymptoms">
          <PencilSquareIcon v-if="selSymptoms.length" class="h-4 w-4" aria-hidden="true" />
          <PlusIcon v-else class="h-4 w-4" aria-hidden="true" />
          {{ selSymptoms.length ? $t('symptoms.calendar.edit') : $t('symptoms.calendar.add') }}
        </button>
      </div>
    </DaySheet>

    <BottomSheet v-if="symptomsFor" :title="symptomsTitle" :close-label="$t('calendar.close')" @close="closeSymptoms">
      <SymptomPicker :date="symptomsFor" />
      <button type="button" class="btn btn-primary mt-4 w-full" @click="closeSymptoms">{{ $t('symptoms.done') }}</button>
    </BottomSheet>
  </div>
</template>

<style scoped>
.nav-btn { display: grid; place-items: center; width: 2.75rem; height: 2.75rem; border-radius: 9999px; color: var(--color-ink); }
.nav-btn:disabled { opacity: .3; }
@media (hover: hover) { .nav-btn:not(:disabled):hover { background: var(--color-surface-muted); } }
.today-btn { flex: none; font-size: .8125rem; font-weight: 600; color: var(--color-primary); background: var(--color-primary-soft); padding: .25rem .75rem; border-radius: 9999px; }
.grid-wrap { overflow: hidden; touch-action: pan-y; padding-top: .375rem; }
.month-label { font-family: var(--font-display); font-size: 1.125rem; font-weight: 560; padding: .5rem .25rem .125rem; border-top: 1px solid var(--color-line); color: var(--color-ink); }

.legend { display: flex; flex-wrap: wrap; gap: .5rem 1.1rem; font-size: .75rem; color: var(--color-ink-soft); }
.legend li { display: inline-flex; align-items: center; gap: .4rem; }
.sw { display: inline-block; width: 1.0625rem; height: 1.0625rem; border-radius: .4rem; }
.sw-logged { background: var(--color-period); width: 1.5rem; border-radius: 9999px; }
.sw-scale { display: inline-flex; gap: 2px; }
.sw-pred { width: .8125rem; height: 1.0625rem; border-radius: .3rem;
  background: color-mix(in srgb, var(--color-period) calc(var(--tile-t0) + var(--tile-t1) * var(--s)), var(--color-surface));
  border: 1.5px dashed color-mix(in srgb, var(--color-period) calc(var(--edge-t0) + 50% * var(--s)), transparent); }
.sw-fertile { background: color-mix(in srgb, var(--color-fertile) calc(var(--ftile-t0) + var(--ftile-t1) * .7), var(--fertile-base)); border: 1.5px solid color-mix(in srgb, var(--color-fertile) calc(var(--edge-t0) + 28%), transparent); }
.sw-ov { display: inline-block; width: .6875rem; height: .6875rem; border-radius: 9999px; border: 2px solid var(--color-fertile); }
.sw-win { display: inline-block; width: 1.25rem; height: 3px; border-radius: 9999px; background: var(--color-period); }
.sw-start { display: inline-block; width: .375rem; height: .375rem; border-radius: 9999px; background: var(--color-period); }
.sw-today { border: 2px solid var(--color-ink); }
.sw-noted { display: inline-block; width: .5rem; height: .5rem; border-radius: 9999px; background: var(--color-luteal); }
.sym-btn { display: inline-flex; align-items: center; gap: .375rem; min-height: 2.75rem; padding: 0 1rem; border-radius: 9999px; font-size: .9375rem; font-weight: 600; color: var(--color-primary); background: var(--color-primary-soft); }

@media (prefers-reduced-motion: no-preference) {
  .slide-next-enter-active, .slide-next-leave-active, .slide-prev-enter-active, .slide-prev-leave-active { transition: transform .2s ease, opacity .2s ease; }
  .slide-next-enter-from, .slide-prev-leave-to { transform: translateX(var(--dx, 24px)); opacity: 0; }
  .slide-next-leave-to, .slide-prev-enter-from { transform: translateX(-24px); opacity: 0; }
  .slide-prev-enter-from { transform: translateX(-24px); }
  .slide-prev-leave-to { transform: translateX(24px); }
}
</style>
