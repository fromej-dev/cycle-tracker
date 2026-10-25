<script setup lang="ts">
/**
 * CycleRing: the signature dial. Pure SVG, no dependencies, presentational only.
 *
 * One lap = one cycle (day 1 at 12 o'clock, clockwise). Layers, bottom to top:
 *   track + day dots, fertile window (soft), predicted next period (fuzzy: per-day
 *   opacity follows p_start, then blurred), logged period (solid), ovulation dot, today marker.
 * Certainty is visible before any number is read: a regular cycle gives a short,
 * dark, crisp arc; an irregular one a long, pale, smeared arc.
 */
import { computed } from 'vue';

interface Props {
  /** days on the dial (one lap) */
  length: number;
  /** 0-based index of today within the cycle */
  todayIdx: number | null;
  /** logged period days, solid, starting at day 1 */
  periodDays?: number;
  /** extra expected period days after the logged ones (ongoing period), drawn pale */
  periodExpectedExtra?: number;
  fertile?: { start: number; end: number } | null;
  ovulationIdx?: number | null;
  /** predicted next-period density: [{ idx, p }] */
  forecast?: { idx: number; p: number }[];
  mostLikelyIdx?: number | null;
  empty?: boolean;
}
const props = withDefaults(defineProps<Props>(), {
  periodDays: 0,
  periodExpectedExtra: 0,
  fertile: null,
  ovulationIdx: null,
  forecast: () => [],
  mostLikelyIdx: null,
  empty: false,
});

const C = 170; // centre of the 340 viewBox
const R = 142; // radius of the ring centre line
const W = 22; // ring thickness
const N = computed(() => Math.max(props.length, 7));

const rad = (idx: number) => ((-90 + (360 * idx) / N.value) * Math.PI) / 180;
const pt = (idx: number, r = R) => ({ x: C + r * Math.cos(rad(idx)), y: C + r * Math.sin(rad(idx)) });

function arc(i0: number, i1: number, r = R): string {
  const a = pt(i0, r);
  const b = pt(i1, r);
  const large = ((i1 - i0) / N.value) * 360 > 180 ? 1 : 0;
  return `M ${a.x.toFixed(2)} ${a.y.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;
}

// round caps stick out by W/2; pull the ends in so arcs end where the data ends
const capDays = computed(() => (W / 2 / R / (2 * Math.PI)) * N.value);

const periodPath = computed(() => {
  if (props.periodDays <= 0) return null;
  const cap = capDays.value;
  const end = Math.min(props.periodDays, N.value);
  // a single-day period still needs to read as a blob
  return end - 2 * cap < 0.05 ? arc(0.3, 0.7) : arc(cap, end - cap);
});
const extraPath = computed(() => {
  if (props.periodExpectedExtra <= 0 || props.periodDays <= 0) return null;
  const cap = capDays.value;
  const start = props.periodDays + cap;
  const end = Math.min(props.periodDays + props.periodExpectedExtra, N.value) - cap;
  return end > start ? arc(start, end) : null;
});
const fertilePath = computed(() => {
  if (!props.fertile) return null;
  const a = Math.max(0, props.fertile.start);
  const b = Math.min(N.value, props.fertile.end + 1);
  if (b <= a) return null;
  const cap = capDays.value;
  return b - a - 2 * cap > 0.05 ? arc(a + cap, b - cap) : arc(a + 0.3, b - 0.3);
});

const PEAK = 0.2; // p_start of a "sharp" forecast day; fully opaque at/above this
const forecastSegs = computed(() => {
  // sample the per-day density at quarter-day steps (linear between day centres) so the arc is smooth, not banded
  const pts = [...props.forecast].sort((x, y) => x.idx - y.idx);
  if (!pts.length) return [];
  const at = (t: number) => {
    const c = t - 0.5;
    const lo = Math.floor(c);
    const a = pts.find((d) => d.idx === lo)?.p ?? 0;
    const b = pts.find((d) => d.idx === lo + 1)?.p ?? 0;
    return a + (b - a) * (c - lo);
  };
  const first = pts[0].idx;
  const last = pts[pts.length - 1].idx + 1;
  const out: { key: number; d: string; o: number }[] = [];
  for (let t = first; t < last; t += 0.25) {
    const p = at(t + 0.125);
    const i0 = Math.max(0, t);
    const i1 = Math.min(N.value, t + 0.262);
    if (p > 0.004 && i1 > i0) out.push({ key: t, d: arc(i0, i1), o: Math.min(1, Math.pow(p / PEAK, 0.7)) * 0.95 });
  }
  return out;
});

const dots = computed(() => Array.from({ length: N.value > 45 ? 0 : N.value }, (_, i) => pt(i + 0.5, R - W / 2 - 13)));
const today = computed(() => (props.todayIdx === null ? null : pt(Math.min(props.todayIdx, N.value - 1) + 0.5)));
const ovulation = computed(() => (props.ovulationIdx === null || props.ovulationIdx < 0 || props.ovulationIdx >= N.value ? null : pt(props.ovulationIdx + 0.5)));
const onPeriod = computed(() => props.todayIdx !== null && props.todayIdx < props.periodDays);
const peak = computed(() => (props.mostLikelyIdx === null || props.mostLikelyIdx < 0 || props.mostLikelyIdx >= N.value ? null : pt(props.mostLikelyIdx + 0.5)));
</script>

<template>
  <div class="cycle-ring">
    <div class="ring-plate" aria-hidden="true"></div>
    <svg viewBox="0 0 340 340" class="ring-svg" role="img" aria-hidden="true" focusable="false">
      <defs>
        <filter id="ring-fuzz" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="2" />
        </filter>
      </defs>

      <circle :cx="C" :cy="C" :r="R" fill="none" :stroke-width="W" class="track" />
      <circle v-for="(d, i) in dots" :key="i" :cx="d.x" :cy="d.y" r="1.7" class="dot" />

      <path v-if="fertilePath" :d="fertilePath" fill="none" :stroke-width="W" stroke-linecap="round" class="fertile ring-fade" />

      <g v-if="!empty" filter="url(#ring-fuzz)" class="ring-fade">
        <path v-for="s in forecastSegs" :key="s.key" :d="s.d" fill="none" :stroke-width="W" class="forecast" :style="{ strokeOpacity: s.o }" />
      </g>
      <circle v-if="peak" :cx="peak.x" :cy="peak.y" r="2.6" class="peak ring-fade" />

      <path v-if="extraPath" :d="extraPath" fill="none" :stroke-width="W" stroke-linecap="round" class="period-extra ring-fade" />
      <path v-if="periodPath" :d="periodPath" fill="none" :stroke-width="W" stroke-linecap="round" class="period ring-fade" />

      <g v-if="ovulation" class="ring-fade">
        <circle :cx="ovulation.x" :cy="ovulation.y" r="9" class="ovu-halo" />
        <circle :cx="ovulation.x" :cy="ovulation.y" r="4.5" class="ovu" />
      </g>

      <g v-if="today && !empty" class="ring-fade" :class="{ 'on-period': onPeriod }">
        <circle :cx="today.x" :cy="today.y" r="13" class="today-bg" />
        <circle :cx="today.x" :cy="today.y" r="13" fill="none" stroke-width="3.5" class="today-ring" />
        <circle :cx="today.x" :cy="today.y" r="4.5" class="today-dot" />
      </g>
    </svg>
    <div class="ring-center"><slot /></div>
  </div>
</template>

<style scoped>
.cycle-ring { position: relative; width: 100%; max-width: 22.5rem; aspect-ratio: 1; margin-inline: auto; }
.ring-plate {
  position: absolute; inset: 11.5%; border-radius: 9999px;
  background: radial-gradient(circle at 50% 38%, var(--color-surface) 0%, var(--color-surface) 62%, color-mix(in srgb, var(--color-surface-muted) 55%, var(--color-surface)) 100%);
  box-shadow: 0 1px 2px rgb(60 30 50 / .05), 0 18px 40px -22px rgb(60 30 50 / .35);
}
:global(.dark) .ring-plate { box-shadow: 0 1px 0 rgb(255 255 255 / .04) inset, 0 20px 44px -22px rgb(0 0 0 / .8); }
.ring-svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.ring-center {
  position: absolute; inset: 22%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
}
.track { stroke: var(--color-surface-muted); }
.dot { fill: var(--color-line-strong); opacity: .75; }
.fertile { stroke: var(--color-fertile); stroke-opacity: .42; }
.forecast { stroke: var(--color-period); }
.peak { fill: var(--color-on-phase); opacity: .9; }
.period { stroke: var(--color-period); }
.period-extra { stroke: var(--color-period); stroke-opacity: .28; }
.ovu-halo { fill: var(--color-surface); }
.ovu { fill: var(--color-fertile); }
.today-bg { fill: var(--color-surface); filter: drop-shadow(0 2px 4px rgb(40 20 40 / .28)); }
.today-ring { stroke: var(--color-ink); }
.today-dot { fill: var(--color-ink); }
.on-period .today-bg { fill: transparent; filter: none; }
.on-period .today-ring { stroke: var(--color-on-phase); }
.on-period .today-dot { fill: var(--color-on-phase); }

@media (prefers-reduced-motion: no-preference) {
  .ring-fade { animation: ring-in .8s ease-out both; }
}
@keyframes ring-in { from { opacity: 0; } to { opacity: 1; } }
</style>
