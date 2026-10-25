<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  addDays, addMonths, differenceInCalendarDays, endOfMonth, format, formatISO, isSameMonth, parseISO,
  startOfDay, startOfMonth, startOfWeek, subDays,
} from 'date-fns';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/vue/24/outline';
import CalendarDay from '@/components/CalendarDay.vue';
import DaySheet, { type Fact } from '@/components/DaySheet.vue';
import { usePeriodsStore } from '@/stores/periods';
import { useReportsStore } from '@/stores/reports';
import { useCalendarForecast } from '@/composables/useCalendarForecast';
import { dfLocale, formatDay, formatBetween } from '@/utils/formatDate';

const { t, locale } = useI18n();
const periodsStore = usePeriodsStore();
const reports = useReportsStore();
const { forecast, reason, byDate, prob, ovulation, lastCovered } = useCalendarForecast();

const iso = (d: Date) => formatISO(d, { representation: 'date' });
const today = startOfDay(new Date());
const todayISO = iso(today);

onMounted(() => {
  periodsStore.fetchPeriods(1, 100);
  reports.fetchForecast();
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

const info = (c: Cell) => {
  const lg = loggedMap.value.get(c.iso);
  const pr = lg ? null : prob(c.iso);
  return {
    logged: !!lg,
    joinPrev: !!lg && c.col > 0 && !!loggedMap.value.get(iso(subDays(parseISO(c.iso), 1))),
    joinNext: !!lg && c.col < 6 && !!loggedMap.value.get(iso(addDays(parseISO(c.iso), 1))),
    pBleeding: pr?.p_bleeding ?? 0,
    pFertile: pr && (pr.p_bleeding ?? 0) < 0.04 ? pr.p_fertile : 0,
    ovulation: !lg && ovulation.value === c.iso,
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
const beyond = computed(() => !reason.value && !!lastCovered.value && shownEnd.value > parseISO(lastCovered.value) && shownEnd.value > today);
const beyondAll = computed(() => !reason.value && !!lastCovered.value && startOfMonth(month.value) > parseISO(lastCovered.value));
const hasFertile = computed(() => !reason.value && [...byDate.value.values()].some((v) => v.p_fertile >= 0.08));
const hasPred = computed(() => !reason.value && [...byDate.value.values()].some((v) => v.p_bleeding >= 0.04));

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
  } else if (pr && pr.p_bleeding >= 0.04) {
    out.push({ tone: 'predicted', text: t('calendar.facts.chance', { pct: pct(pr.p_bleeding) }), sub: t('calendar.facts.predictionNote') });
  }
  if (!lg && ovulation.value === s) out.push({ tone: 'fertile', text: t('calendar.facts.ovulation') });
  else if (!lg && pr && pr.p_fertile >= 0.08 && pr.p_bleeding < 0.04) out.push({ tone: 'fertile', text: t('calendar.facts.fertile'), sub: t('calendar.facts.fertileChance', { pct: pct(pr.p_fertile) }) });
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

const dayLabel = (c: Cell) => {
  const lg = loggedMap.value.get(c.iso);
  const pr = lg ? null : prob(c.iso);
  const base = formatDay(c.iso, locale.value, true) ?? '';
  if (lg) return `${base}, ${t('calendar.facts.logged', { n: lg.day })}`;
  if (pr && pr.p_bleeding >= 0.04) return `${base}, ${t('calendar.facts.chance', { pct: pct(pr.p_bleeding) })}`;
  return base;
};
</script>

<template>
  <div class="mx-auto max-w-lg px-3 pt-5 pb-8">
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
      <li v-if="hasPred"><span class="sw-scale"><i class="sw sw-pred" style="--s:.3"></i><i class="sw sw-pred" style="--s:.6"></i><i class="sw sw-pred" style="--s:1"></i></span>{{ $t('calendar.legend.predicted') }}</li>
      <li v-if="hasFertile"><span class="sw sw-fertile"></span>{{ $t('calendar.legend.fertile') }}</li>
      <li v-if="hasFertile"><span class="sw-ov"></span>{{ $t('calendar.legend.ovulation') }}</li>
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
        @end="endHere" />
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
  background: color-mix(in srgb, var(--color-period) calc(7% + 30% * var(--s)), var(--color-surface));
  border: 1.5px dashed color-mix(in srgb, var(--color-period) calc(35% + 55% * var(--s)), transparent); }
.sw-fertile { background: color-mix(in srgb, var(--color-fertile) 26%, var(--color-surface)); }
.sw-ov { display: inline-block; width: .4rem; height: .4rem; border-radius: 9999px; background: var(--color-fertile); }
.sw-today { border: 2px solid var(--color-ink); }

@media (prefers-reduced-motion: no-preference) {
  .slide-next-enter-active, .slide-next-leave-active, .slide-prev-enter-active, .slide-prev-leave-active { transition: transform .2s ease, opacity .2s ease; }
  .slide-next-enter-from, .slide-prev-leave-to { transform: translateX(var(--dx, 24px)); opacity: 0; }
  .slide-next-leave-to, .slide-prev-enter-from { transform: translateX(-24px); opacity: 0; }
  .slide-prev-enter-from { transform: translateX(-24px); }
  .slide-prev-leave-to { transform: translateX(24px); }
}
</style>
