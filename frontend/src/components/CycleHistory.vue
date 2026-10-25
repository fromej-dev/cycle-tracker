<script setup lang="ts">
/**
 * "Your cycles": one row per past cycle, aligned at day 1, newest on top. The period is solid, the estimated
 * fertile window is green, the band behind everything is this person's typical range (average +- spread).
 * A gap of ~2x the usual length is drawn hatched and called a possible missed log, not a 74-day cycle.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { differenceInCalendarDays, parseISO } from 'date-fns';
import { usePeriodsStore } from '@/stores/periods';
import { localToday } from '@/api/plan';
import { formatRange, formatShort } from '@/utils/formatDate';
import Skeleton from '@/components/Skeleton.vue';

const props = defineProps<{ limit?: number }>();
const { t, locale } = useI18n();
const store = usePeriodsStore();
const loaded = ref(false);
onMounted(async () => { await store.fetchPeriods(1, 100); loaded.value = true; });

interface Row { key: number; start: string; length: number; open: boolean; periodDays: number; fertile: [number, number] | null; gap: boolean; periodEnd: string | null }
const today = localToday();

const base = computed(() => {
  const ps = [...store.periods].sort((a, b) => a.start_date.localeCompare(b.start_date));
  const raw = ps.map((p, i) => {
    const next = ps[i + 1];
    const open = !next;
    const length = next ? differenceInCalendarDays(parseISO(next.start_date), parseISO(p.start_date)) : differenceInCalendarDays(parseISO(today), parseISO(p.start_date)) + 1;
    const pd = p.end_date ? differenceInCalendarDays(parseISO(p.end_date), parseISO(p.start_date)) + 1 : Math.min(length, differenceInCalendarDays(parseISO(today), parseISO(p.start_date)) + 1);
    return { key: p.id, start: p.start_date, length, open, periodDays: Math.max(1, pd), periodEnd: p.end_date };
  });
  const done = raw.filter((r) => !r.open).map((r) => r.length).sort((a, b) => a - b);
  const median = done.length ? done[Math.floor(done.length / 2)] : 28;
  return { raw, median };
});

const rows = computed<Row[]>(() => base.value.raw.map((r) => {
  const gap = !r.open && r.length > Math.max(base.value.median * 1.7, 45);
  const ov = r.length - 14; // day number of ovulation, from a 14-day luteal phase
  const fertile: [number, number] | null = !r.open && !gap && r.length >= 21 && r.length <= 45 ? [Math.max(1, ov - 5), ov + 1] : null;
  return { ...r, gap, fertile };
}).reverse());

const stats = computed(() => {
  const ls = rows.value.filter((r) => !r.open && !r.gap).map((r) => r.length);
  if (ls.length < 2) return null;
  const avg = ls.reduce((a, b) => a + b, 0) / ls.length;
  const sd = Math.sqrt(ls.reduce((a, b) => a + (b - avg) ** 2, 0) / ls.length);
  // the band is built from the SAME rounded numbers that are printed ("29 ± 1 days" = 28 to 30 days)
  const a = Math.round(avg), d = Math.max(1, Math.round(sd));
  return { avg: a, sd: d, lo: a - d, hi: a + d, n: ls.length };
});
const shown = computed(() => (props.limit ? rows.value.slice(0, props.limit) : rows.value));
const axis = computed(() => {
  const m = Math.max(35, ...shown.value.filter((r) => !r.gap).map((r) => r.length), stats.value ? stats.value.hi : 0);
  return Math.ceil((m + 1) / 7) * 7;
});
const ticks = computed(() => { const o: number[] = []; for (let d = 1; d <= axis.value; d += 7) o.push(d); return o; });
const pos = (day: number) => `${((day - 1) / axis.value) * 100}%`;
const w = (days: number) => `${Math.min(days, axis.value + 1 - 1) / axis.value * 100}%`;
const clipped = (r: Row) => r.length > axis.value;

const openKey = ref<number | null>(null);
const cycleEnd = (r: Row) => { const d = parseISO(r.start); d.setDate(d.getDate() + r.length - 1); return d; };
const label = (r: Row) => (r.open ? t('history.current', { n: r.length }) : t('common.dayN', r.length));
const verdict = (r: Row) => {
  if (r.open) return null;
  if (r.gap) return t('history.gap');
  if (stats.value && (r.length < stats.value.lo || r.length > stats.value.hi)) return r.length < stats.value.avg ? t('history.short') : t('history.long');
  return stats.value ? t('history.typical') : null;
};
</script>

<template>
  <div>
    <Skeleton v-if="!loaded && !store.periods.length" variant="rows" :rows="3" />
    <p v-else-if="!rows.length" class="text-[0.9375rem] leading-snug text-ink-soft">{{ $t('history.empty') }}</p>
    <template v-else>
      <div v-if="stats" class="mb-5 grid grid-cols-2 items-end gap-6 border-y border-line py-4">
        <div><p class="eyebrow">{{ $t('history.average') }}</p><p class="mt-2 font-display text-[1.625rem] leading-none whitespace-nowrap">{{ $t('insights.cyclePlusMinus', { avg: stats.avg, sd: stats.sd }) }}</p></div>
        <p class="text-[0.8125rem] leading-snug text-ink-soft">{{ $t('history.basedOn', { n: stats.n }) }}</p>
      </div>

      <div class="hist relative">
        <div v-if="stats" class="band" aria-hidden="true" :style="{ left: `${((stats.lo - 0.5) / axis) * 100}%`, width: `${((stats.hi - stats.lo + 1) / axis) * 100}%` }"></div>
        <div class="ticks relative" aria-hidden="true">
          <span v-for="d in ticks" :key="d" :style="{ left: pos(d) }">{{ d }}</span>
        </div>
        <ul class="relative flex flex-col">
          <li v-for="r in shown" :key="r.key">
            <button type="button" class="row" :aria-expanded="openKey === r.key" @click="openKey = openKey === r.key ? null : r.key">
              <span class="flex items-baseline justify-between gap-3">
                <span class="min-w-0"><span class="font-display text-[1.125rem] leading-none">{{ label(r) }}</span><span class="ml-2 text-[0.75rem] text-ink-soft">{{ $t('history.from', { date: formatShort(r.start, locale) }) }}</span></span>
                <span class="text-right text-[0.75rem] text-ink-soft" :class="{ 'gap-note': r.gap }">{{ verdict(r) }}</span>
              </span>
              <span class="bar-wrap" aria-hidden="true">
                <span class="track" :class="{ gap: r.gap, open: r.open }" :style="{ width: w(r.length) }">
                  <i class="period" :style="{ width: `${(Math.min(r.periodDays, r.length) / Math.min(r.length, axis)) * 100}%` }"></i>
                  <i v-if="r.fertile" class="fertile" :style="{ left: `${((r.fertile[0] - 1) / r.length) * 100}%`, width: `${((r.fertile[1] - r.fertile[0] + 1) / r.length) * 100}%` }"></i>
                </span>
                <span v-if="r.open" class="today-mark" :style="{ left: `${((r.length - 0.5) / axis) * 100}%` }"><i></i><b>{{ $t('history.today') }}</b></span>
                <span v-if="clipped(r)" class="clip">…</span>
              </span>
            </button>
            <div v-if="openKey === r.key" class="detail">
              <p class="font-semibold">{{ formatRange(r.start, r.open ? null : cycleEnd(r).toISOString().slice(0, 10), locale) }}<template v-if="r.open"> → {{ $t('history.now') }}</template></p>
              <p class="text-ink-soft">{{ $t('history.periodDays', { n: r.periodDays }) }}<template v-if="r.periodEnd === null && r.open"> · {{ $t('history.ongoingOrJust') }}</template></p>
              <p v-if="r.fertile" class="text-ink-soft">{{ $t('history.fertileEst', { a: r.fertile[0], b: r.fertile[1] }) }}</p>
              <p v-if="r.gap" class="text-ink-soft">{{ $t('history.gapDetail', { n: r.length, usual: stats?.avg ?? base.median }) }}</p>
            </div>
          </li>
        </ul>
      </div>

      <p class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-soft">
        <span class="inline-flex items-center gap-1.5"><i class="lg period"></i>{{ $t('history.legendPeriod') }}</span>
        <span class="inline-flex items-center gap-1.5"><i class="lg fertile"></i>{{ $t('history.legendFertile') }}</span>
        <span v-if="stats" class="inline-flex items-center gap-1.5"><i class="lg band2"></i>{{ $t('history.legendTypical') }}</span>
      </p>
    </template>
  </div>
</template>

<style scoped>
.band { position: absolute; top: 1.5rem; bottom: 0; border-radius: .75rem; background: color-mix(in srgb, var(--color-luteal) 11%, transparent); border-inline: 1.5px dashed color-mix(in srgb, var(--color-luteal) 35%, transparent); }
.ticks { height: 1.5rem; }
.ticks span { position: absolute; top: 0; font-size: .6875rem; color: var(--color-ink-soft); font-variant-numeric: tabular-nums; transform: translateX(-1px); }
.row { display: flex; flex-direction: column; gap: .5rem; width: 100%; padding: .75rem 0 .5rem; text-align: left; min-height: 3.5rem; }
.bar-wrap { position: relative; display: block; height: 1.125rem; }
.track { position: relative; display: block; height: 100%; border-radius: 9999px; background: color-mix(in srgb, var(--color-ink) 11%, var(--color-surface)); overflow: hidden; }
.track.open { background: color-mix(in srgb, var(--color-ink) 6%, var(--color-surface)); }
.track.gap { background: repeating-linear-gradient(135deg, color-mix(in srgb, var(--color-luteal) 40%, transparent) 0 2px, transparent 2px 7px); outline: 1.5px dashed color-mix(in srgb, var(--color-luteal) 70%, transparent); outline-offset: -1.5px; }
.period, .fertile { position: absolute; top: 0; bottom: 0; display: block; }
.period { left: 0; background: var(--color-period); border-radius: 9999px; }
.fertile { background: var(--color-fertile); border-radius: 9999px; top: 22%; bottom: 22%; }
.today-mark { position: absolute; top: -.125rem; bottom: -.125rem; width: 0; }
.today-mark i { position: absolute; left: -1px; top: 0; bottom: 0; width: 2px; border-radius: 1px; background: var(--color-ink); opacity: .55; }
.today-mark b { position: absolute; left: .375rem; top: 50%; transform: translateY(-50%); font-size: .6875rem; font-weight: 600; color: var(--color-ink-soft); white-space: nowrap; }
.clip { position: absolute; right: 2px; top: -2px; font-weight: 700; color: var(--color-ink-soft); background: var(--color-surface); padding: 0 .25rem; border-radius: .5rem; line-height: 1.2; }
.gap-note { color: var(--color-luteal-ink); font-weight: 600; }
.detail { margin: .125rem 0 .5rem; padding: .75rem 1rem; border-radius: 1.125rem; background: var(--color-surface-muted); font-size: .875rem; line-height: 1.4; position: relative; }
.lg { display: inline-block; width: 1.25rem; height: .5rem; border-radius: 9999px; }
.lg.period { background: var(--color-period); position: static; }
.lg.fertile { background: var(--color-fertile); position: static; }
.lg.band2 { height: .75rem; background: color-mix(in srgb, var(--color-luteal) 18%, transparent); border: 1.5px dashed color-mix(in srgb, var(--color-luteal) 50%, transparent); border-radius: .25rem; }
</style>
