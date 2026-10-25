<script setup lang="ts">
/**
 * CycleRing: the signature dial. Pure SVG, no dependencies, presentational only.
 * One lap = one cycle, day 1 at 12 o'clock, clockwise. Every mark means one thing:
 *   solid thick arc ....... logged period (the past)
 *   thin inner arc ........ fertile window
 *   hollow bubbles ........ FORECAST of the next period start, one per day: the bubble's size and
 *                           fill grow with p_start, so a regular cycle is a few big filled bubbles and an
 *                           irregular one many small faint ones. Date labels sit at the 80% range ends.
 *   dashed line ........... days overdue
 *   ink pill on the ring .. today
 */
import { computed } from 'vue';

interface Props {
  length: number;
  todayIdx: number | null;
  dayLabel?: string;
  periodDays?: number;
  periodExpectedExtra?: number;
  fertile?: { start: number; end: number } | null;
  fertilePast?: boolean;
  forecast?: { idx: number; p: number }[];
  rangeLabels?: { idx: number; text: string }[];
  overdue?: { start: number; end: number } | null;
  empty?: boolean;
}
const props = withDefaults(defineProps<Props>(), {
  dayLabel: '',
  periodDays: 0,
  periodExpectedExtra: 0,
  fertile: null,
  fertilePast: false,
  forecast: () => [],
  rangeLabels: () => [],
  overdue: null,
  empty: false,
});

const C = 180;
const R = 143;
const W = 30;
const N = computed(() => Math.max(props.length, 7));

const ang = (idx: number) => -90 + (360 * idx) / N.value;
const rad = (idx: number) => (ang(idx) * Math.PI) / 180;
const pt = (idx: number, r = R) => ({ x: C + r * Math.cos(rad(idx)), y: C + r * Math.sin(rad(idx)) });

function arc(i0: number, i1: number, r = R): string {
  const a = pt(i0, r);
  const b = pt(i1, r);
  const large = ((i1 - i0) / N.value) * 360 > 180 ? 1 : 0;
  return `M ${a.x.toFixed(2)} ${a.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;
}

const capDays = (w: number, r = R) => (w / 2 / r / (2 * Math.PI)) * N.value;

const periodPath = computed(() => {
  if (props.periodDays <= 0) return null;
  const cap = capDays(W);
  const end = Math.min(props.periodDays, N.value);
  return end - 2 * cap < 0.05 ? arc(0.3, 0.7) : arc(cap, end - cap);
});
const extraPath = computed(() => {
  if (props.periodExpectedExtra <= 0 || props.periodDays <= 0) return null;
  const cap = capDays(W);
  const start = props.periodDays + cap;
  const end = Math.min(props.periodDays + props.periodExpectedExtra, N.value) - cap;
  return end > start ? arc(start, end) : null;
});

const FW = 10;
const FR = R - W / 2 + FW / 2 + 3;
const fertilePath = computed(() => {
  if (!props.fertile) return null;
  const a = Math.max(0, props.fertile.start);
  const b = Math.min(N.value, props.fertile.end + 1);
  if (b <= a) return null;
  const cap = capDays(FW, FR);
  return b - a - 2 * cap > 0.05 ? arc(a + cap, b - cap, FR) : arc(a + 0.3, b - 0.3, FR);
});

const overduePath = computed(() => {
  if (!props.overdue) return null;
  const a = Math.max(0, props.overdue.start);
  const b = Math.min(N.value, props.overdue.end + 1);
  return b > a ? arc(a, b) : null;
});

const PEAK = 0.2; // p_start of a "sharp" forecast day
const bubbles = computed(() =>
  props.forecast
    .filter((d) => d.idx >= 0 && d.idx < N.value && d.p > 0.006)
    .map((d) => {
      const x = Math.min(1, Math.sqrt(d.p / PEAK));
      const c = pt(d.idx + 0.5);
      return { key: d.idx, cx: c.x, cy: c.y, r: 3 + (W / 2 - 1.5 - 3) * x, fill: 0.1 + 0.8 * x * x, line: 0.45 + 0.55 * x };
    }),
);

const labels = computed(() =>
  props.rangeLabels
    .filter((l) => l.idx >= 0 && l.idx < N.value)
    .map((l) => {
      const c = pt(l.idx + 0.5, R + W / 2 + 12);
      const cos = Math.cos(rad(l.idx + 0.5));
      return { ...l, x: c.x, y: c.y + 4, anchor: cos > 0.35 ? 'start' : cos < -0.35 ? 'end' : 'middle' };
    }),
);

const onPeriod = computed(() => props.todayIdx !== null && props.todayIdx < props.periodDays);
const today = computed(() => (props.todayIdx === null ? null : pt(Math.min(props.todayIdx, N.value - 1) + 0.5)));
// when today sits on the period arc the pill steps inside the plate so it never hides the arc
const pillPos = computed(() => (props.todayIdx === null ? null : pt(Math.min(props.todayIdx, N.value - 1) + 0.5, onPeriod.value ? R - W / 2 - 17 : R)));
const pillW = computed(() => 20 + props.dayLabel.length * 7.2);
</script>

<template>
  <div class="cycle-ring">
    <svg viewBox="0 0 360 360" class="ring-svg" role="img" :aria-label="dayLabel" focusable="false">
      <circle :cx="C" :cy="C" :r="R - W / 2 - 1" class="plate" />
      <circle :cx="C" :cy="C" :r="R" fill="none" :stroke-width="W" class="track" />

      <path v-if="fertilePath" :d="fertilePath" fill="none" :stroke-width="FW" stroke-linecap="round" class="fertile ring-fade" :style="{ strokeOpacity: fertilePast ? 0.4 : 1 }" />

      <path v-if="overduePath" :d="overduePath" fill="none" stroke-width="3" stroke-linecap="round" stroke-dasharray="0.1 9" class="overdue ring-fade" />

      <path v-if="empty" :d="arc(0.4, 5.6)" fill="none" stroke-width="6" stroke-linecap="round" stroke-dasharray="0.1 13" class="ghost" />

      <g v-if="!empty" class="ring-fade">
        <circle v-for="b in bubbles" :key="b.key" :cx="b.cx" :cy="b.cy" :r="b.r" class="bubble" :style="{ fillOpacity: b.fill, strokeOpacity: b.line }" />
      </g>

      <path v-if="extraPath" :d="extraPath" fill="none" :stroke-width="W" stroke-linecap="round" class="period-extra ring-fade" />
      <path v-if="periodPath" :d="periodPath" fill="none" :stroke-width="W" stroke-linecap="round" class="period ring-fade" />

      <text v-for="l in labels" :key="l.idx" :x="l.x" :y="l.y" :text-anchor="l.anchor" class="range-label ring-fade">{{ l.text }}</text>

      <g v-if="pillPos && today && !empty && dayLabel" class="ring-fade">
        <circle v-if="onPeriod" :cx="today.x" :cy="today.y" r="6.5" class="today-dot" />
        <rect :x="pillPos.x - pillW / 2" :y="pillPos.y - 13" :width="pillW" height="26" rx="13" class="pill" />
        <text :x="pillPos.x" :y="pillPos.y + 4.5" text-anchor="middle" class="pill-text">{{ dayLabel }}</text>
      </g>
    </svg>
    <div class="ring-center"><slot /></div>
  </div>
</template>

<style scoped>
.cycle-ring { position: relative; width: min(calc(100% + 16px), 26rem); aspect-ratio: 1; left: 50%; transform: translateX(-50%); }
.ring-svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.ring-center {
  position: absolute; inset: 21% 20%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
}
.plate { fill: var(--color-surface); stroke: var(--color-line); stroke-width: 1; }
.track { stroke: var(--color-surface-muted); }
.fertile { stroke: var(--color-fertile); }
.period { stroke: var(--color-period); }
.period-extra { stroke: var(--color-period); stroke-opacity: .26; }
.overdue { stroke: var(--color-period); }
.ghost { stroke: var(--color-period); stroke-opacity: .55; }
.bubble { fill: var(--color-period); stroke: var(--color-period); stroke-width: 1.6; }
.range-label { font: 600 11.5px var(--font-sans); fill: var(--color-ink-soft); }
.pill { fill: var(--color-ink); }
.today-dot { fill: var(--color-ink); stroke: var(--color-surface); stroke-width: 2.5; }
.pill-text { font: 700 12.5px var(--font-sans); fill: var(--color-surface); }

@media (prefers-reduced-motion: no-preference) {
  .ring-fade { animation: ring-in .7s ease-out both; }
}
@keyframes ring-in { from { opacity: 0; } to { opacity: 1; } }
</style>
