<script setup lang="ts">
/**
 * CycleRing: the signature dial. Pure SVG, no dependencies, presentational only.
 * One lap = one cycle, day 1 at 12 o'clock, clockwise. Every mark means one thing:
 *   solid thick arc ....... logged period (the past)
 *   thin inner arc ........ fertile window
 *   hollow bubbles ........ FORECAST of the next period start, one per day: the bubble's size and
 *                           fill grow with p_start, so a regular cycle is a few big filled bubbles and an
 *                           irregular one many small faint ones. Date labels sit at the 80% range ends.
 *   bracket + label ....... the 80% range as ONE span ("3–7 Nov")
 *   tinted track .......... how far this cycle has come (period start to today)
 *   dotted trail .......... days overdue (legend: "Overdue")
 *   ink dot on the ring ... today, with its "Day N" pill attached just inside
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
  ovulationIdx?: number | null;
  forecast?: { idx: number; p: number }[];
  rangeSpan?: { start: number; end: number; text: string } | null;
  overdue?: { start: number; end: number } | null;
  empty?: boolean;
}
const props = withDefaults(defineProps<Props>(), {
  dayLabel: '',
  periodDays: 0,
  periodExpectedExtra: 0,
  fertile: null,
  fertilePast: false,
  ovulationIdx: null,
  forecast: () => [],
  rangeSpan: null,
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
const RMAX = 11.5; // neighbours are ~24px apart on the ring: the biggest bubble must not touch the next one
const bubbles = computed(() =>
  props.forecast
    .filter((d) => d.idx >= 0 && d.idx < N.value && d.p > 0.006 && (props.todayIdx === null || d.idx > props.todayIdx))
    .map((d) => {
      const x = Math.min(1, d.p / PEAK) ** 0.55; // smooth, monotonic size curve
      const c = pt(d.idx + 0.5);
      return { key: d.idx, cx: c.x, cy: c.y, r: 3.2 + (RMAX - 3.2) * x, fill: 0.2 + 0.8 * x * x, line: 0.85 + 0.15 * x };
    }),
);

const ovMark = computed(() => {
  if (props.ovulationIdx === null || props.ovulationIdx === undefined || !props.fertile) return null;
  if (props.ovulationIdx < 0 || props.ovulationIdx >= N.value) return null;
  return pt(props.ovulationIdx + 0.5, FR);
});

const SR = R + W / 2 + 5;
const span = computed(() => {
  const sp = props.rangeSpan;
  if (!sp) return null;
  // from the CENTRE of the first day to the CENTRE of the last: the ends sit on the bubbles of the dates named
  const a = Math.max(0, sp.start) + 0.5;
  const b = Math.min(N.value, sp.end + 1) - 0.5;
  if (b < a) return null;
  const mid = (a + b) / 2;
  const c = pt(mid, SR + 22);
  const cos = Math.cos((ang(mid) * Math.PI) / 180);
  const tick = (i: number) => ({ a: pt(i, SR - 4), b: pt(i, SR + 3) });
  return {
    d: b - a > 0.05 ? arc(a, b, SR) : null,
    text: sp.text,
    x: c.x,
    y: c.y + 4,
    anchor: cos > 0.6 ? 'start' : cos < -0.6 ? 'end' : 'middle',
    t0: tick(a), t1: tick(b),
  };
});

const tintPath = computed(() => {
  if (props.todayIdx === null || props.empty) return null;
  const end = Math.min(props.todayIdx + 0.5, N.value - 0.01);
  return end > 0.2 ? arc(0, end) : null;
});

const today = computed(() => (props.todayIdx === null ? null : pt(Math.min(props.todayIdx, N.value - 1) + 0.5)));
// the pill sits just inside the track, joined to the today dot by a short stem
const pillPos = computed(() => {
  if (props.todayIdx === null) return null;
  const i = Math.min(props.todayIdx, N.value - 1) + 0.5;
  const inside = pt(i, R - W / 2 - 25);
  // in the upper half the centre text sits right there, so the pill goes outside the ring instead
  return inside.y < C - 45 ? pt(i, R + W / 2 + 24) : inside;
});
const pillW = computed(() => 20 + props.dayLabel.length * 7.2);
</script>

<template>
  <div class="cycle-ring">
    <svg viewBox="0 0 360 360" class="ring-svg" role="img" :aria-label="dayLabel" focusable="false">
      <circle :cx="C" :cy="C" :r="R - W / 2 - 1" class="plate" />
      <circle :cx="C" :cy="C" :r="R" fill="none" :stroke-width="W" class="track" />

      <path v-if="tintPath" :d="tintPath" fill="none" :stroke-width="W" stroke-linecap="round" class="progress ring-fade" />

      <path v-if="fertilePath" :d="fertilePath" fill="none" :stroke-width="FW" stroke-linecap="round" class="fertile ring-fade" />

      <circle v-if="ovMark" :cx="ovMark.x" :cy="ovMark.y" r="6.2" class="ov-mark ring-fade" />
      <path v-if="overduePath" :d="overduePath" fill="none" stroke-width="4.5" stroke-linecap="round" stroke-dasharray="0.1 11" class="overdue ring-fade" />

      <path v-if="empty" :d="arc(0.4, 5.6)" fill="none" stroke-width="6" stroke-linecap="round" stroke-dasharray="0.1 13" class="ghost" />

      <g v-if="!empty" class="ring-fade">
        <g v-for="b in bubbles" :key="b.key">
          <circle :cx="b.cx" :cy="b.cy" :r="b.r" class="bubble-base" />
          <circle :cx="b.cx" :cy="b.cy" :r="b.r" class="bubble" :style="{ fillOpacity: b.fill, strokeOpacity: b.line }" />
        </g>
      </g>

      <path v-if="extraPath" :d="extraPath" fill="none" :stroke-width="W" stroke-linecap="round" class="period-extra ring-fade" />
      <path v-if="periodPath" :d="periodPath" fill="none" :stroke-width="W" stroke-linecap="round" class="period ring-fade" />

      <g v-if="span" class="ring-fade">
        <path v-if="span.d" :d="span.d" fill="none" stroke-width="2" stroke-linecap="round" class="bracket" />
        <line :x1="span.t0.a.x" :y1="span.t0.a.y" :x2="span.t0.b.x" :y2="span.t0.b.y" stroke-width="2" stroke-linecap="round" class="bracket" />
        <line :x1="span.t1.a.x" :y1="span.t1.a.y" :x2="span.t1.b.x" :y2="span.t1.b.y" stroke-width="2" stroke-linecap="round" class="bracket" />
        <text :x="span.x" :y="span.y" :text-anchor="span.anchor" class="range-label">{{ span.text }}</text>
      </g>

      <g v-if="pillPos && today && !empty && dayLabel" class="ring-fade">
        <line :x1="today.x" :y1="today.y" :x2="pillPos.x" :y2="pillPos.y" stroke-width="2.5" class="stem" />
        <circle :cx="today.x" :cy="today.y" r="8" class="today-dot" />
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
.track { stroke: color-mix(in srgb, var(--color-ink) 9%, var(--color-surface)); }
.progress { stroke: color-mix(in srgb, var(--color-period) var(--ring-tint, 20%), transparent); }
.ov-mark { fill: var(--color-surface); stroke: var(--color-fertile); stroke-width: 2.6; }
.bracket { stroke: var(--color-ink-soft); }
.stem { stroke: var(--color-ink); }
.bubble-base { fill: var(--color-surface); }
.fertile { stroke: var(--color-fertile); }
.period { stroke: var(--color-period); }
.period-extra { stroke: var(--color-period); stroke-opacity: .26; }
.overdue { stroke: var(--color-period); }
.ghost { stroke: var(--color-period); stroke-opacity: .55; }
.bubble { fill: var(--color-period); stroke: var(--color-period); stroke-width: 1.8; }
.range-label { paint-order: stroke; stroke: var(--color-background); stroke-width: 5px; stroke-linejoin: round; font: 700 12px var(--font-sans); fill: var(--color-ink); }
.pill { fill: var(--color-ink); stroke: var(--color-surface); stroke-width: 3; paint-order: stroke; }
.today-dot { fill: var(--color-ink); stroke: var(--color-surface); stroke-width: 3; }
.pill-text { font: 700 12.5px var(--font-sans); fill: var(--color-surface); }

@media (prefers-reduced-motion: no-preference) {
  .ring-fade { animation: ring-in .7s ease-out both; }
}
@keyframes ring-in { from { opacity: 0; } to { opacity: 1; } }
</style>
