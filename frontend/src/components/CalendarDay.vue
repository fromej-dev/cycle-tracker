<script setup lang="ts">
/**
 * One day tile. Purely presentational: it is told what is a RECORD (logged) and what is a PREDICTION
 * (pBleeding / pFertile), so the same tile works whichever source supplies the probabilities.
 *   logged  -> solid period colour band, joined to its neighbours
 *   pBleeding -> tinted tile with a dashed edge; the stronger the chance, the stronger the tint
 *   pFertile  -> sage tile, same idea
 */
import { computed } from 'vue';

interface Props {
  day: number;
  logged?: boolean;
  joinPrev?: boolean;
  joinNext?: boolean;
  pBleeding?: number;
  /** 0..1 position inside the fertile window (peak on ovulation); 0 = not fertile */
  fertile?: number;
  projected?: boolean;
  ovulation?: boolean;
  likelyStart?: boolean;
  /** inside the 80% window for the period START: drawn as an underline that joins neighbouring days */
  /** beyond the ~45-day forecast: probabilities are spread thin, so only the clearer days are drawn */
  far?: boolean;
  startWin?: 'only' | 'first' | 'mid' | 'last' | null;
  today?: boolean;
  selected?: boolean;
  /** symptoms were noted on this day */
  noted?: boolean;
  label?: string;
}
const props = withDefaults(defineProps<Props>(), { pBleeding: 0, fertile: 0 });

// Below this a day is not drawn at all: a faint smear across two weeks reads as a 12-day period.
const MIN_NEAR = 0.18;
const MIN_FAR = 0.3;
const kind = computed(() => {
  if (props.logged) return 'logged';
  if (props.pBleeding >= (props.far ? MIN_FAR : MIN_NEAR)) return 'predicted';
  if (props.fertile > 0) return 'fertile';
  return 'none';
});
// steep on purpose: the likely core must look clearly stronger than the tails
const strength = computed(() => {
  if (kind.value === 'predicted') return Math.min(1, Math.max(0, (props.pBleeding - 0.1) / 0.7)) ** 1.25;
  return props.fertile;
});
const style = computed(() => ({ '--s': strength.value.toFixed(3) }));
</script>

<template>
  <button
      type="button"
      class="day"
      :class="[`k-${kind}`, { 'join-prev': joinPrev && logged, 'join-next': joinNext && logged, 'is-today': today, 'is-selected': selected, 'is-ov': ovulation && kind === 'fertile', 'is-proj': projected }]"
      :style="style"
      :aria-label="label"
      :aria-pressed="selected"
      :aria-current="today ? 'date' : undefined"
  >
    <span class="mark" aria-hidden="true"></span>
    <span v-if="startWin" class="swin" :class="`w-${startWin}`" aria-hidden="true"></span>
    <span v-if="today" class="today-ring" aria-hidden="true"></span>
    <span class="num" :class="{ lifted: ovulation || (likelyStart && !logged) }">{{ day }}</span>
    <span v-if="ovulation" class="ov" aria-hidden="true"></span>
    <span v-if="likelyStart && !logged" class="start-dot" aria-hidden="true"></span>
    <span v-if="noted" class="noted" aria-hidden="true"></span>
  </button>
</template>

<style scoped>
.day { position: relative; height: 3rem; display: flex; align-items: center; justify-content: center; border-radius: 1rem; cursor: pointer; -webkit-tap-highlight-color: transparent; }
.num { position: relative; z-index: 2; font: 600 1rem/1 var(--font-sans); font-variant-numeric: tabular-nums; color: var(--color-ink); }
.mark { position: absolute; inset: 0.375rem 0.1875rem; border-radius: 0.875rem; }

.k-logged .mark { inset: 0.375rem 0; background: var(--color-period); border-radius: 9999px; }
.k-logged.join-prev .mark { border-top-left-radius: 0; border-bottom-left-radius: 0; }
.k-logged.join-next .mark { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.k-logged .num { color: var(--color-on-phase); font-weight: 700; }

/* tint/edge strengths come from --tile-t0/--tile-t1 (main.css) so dark mode keeps >= 3:1 against the page */
.k-predicted .mark {
  background: color-mix(in srgb, var(--color-period) calc(var(--tile-t0) + var(--tile-t1) * var(--s)), var(--color-surface));
  border: 1.5px dashed color-mix(in srgb, var(--color-period) calc(var(--edge-t0) + 50% * var(--s)), transparent);
}
.k-fertile .mark {
  background: color-mix(in srgb, var(--color-fertile) calc(var(--ftile-t0) + var(--ftile-t1) * var(--s)), var(--fertile-base));
  border: 1.5px solid color-mix(in srgb, var(--color-fertile) calc(var(--edge-t0) + 40% * var(--s)), transparent);
}
.k-fertile .num { color: var(--color-fertile-ink); }
.k-fertile.is-proj .mark { border-style: dotted; }
.k-fertile.is-ov .mark { border: 2px solid var(--color-fertile); background: color-mix(in srgb, var(--color-fertile) calc(var(--ftile-t0) + var(--ftile-t1)), var(--fertile-base)); }
/* ovulation: a real marker, a ring under the number */
.ov { position: absolute; z-index: 2; bottom: 0.5rem; width: 0.6875rem; height: 0.6875rem; border-radius: 9999px; border: 2px solid var(--color-fertile); background: var(--color-surface); }
.start-dot { position: absolute; z-index: 2; bottom: 0.5rem; width: 0.375rem; height: 0.375rem; border-radius: 9999px; background: var(--color-period); }
/* symptoms noted: a small corner dot that reads on every tile kind */
.noted { position: absolute; z-index: 3; top: 0.3125rem; right: 0.25rem; width: 0.5rem; height: 0.5rem; border-radius: 9999px; background: var(--color-luteal); box-shadow: 0 0 0 1.5px var(--color-surface); }

.swin { position: absolute; z-index: 2; bottom: 0.125rem; height: 3px; left: 0; right: 0; background: var(--color-period); }
.swin.w-only, .swin.w-first { left: 0.5rem; border-top-left-radius: 9999px; border-bottom-left-radius: 9999px; }
.swin.w-only, .swin.w-last { right: 0.5rem; border-top-right-radius: 9999px; border-bottom-right-radius: 9999px; }
.today-ring { position: absolute; inset: 0.375rem 0.1875rem; border-radius: 0.875rem; border: 2px solid var(--color-ink); z-index: 1; }
.k-logged .today-ring { inset: 0.375rem 0; border-radius: 9999px; outline: 2px solid var(--color-ink); outline-offset: 1.5px; border: 0; }
.is-today .mark { border-color: transparent; }
.num.lifted { transform: translateY(-4px); }
.is-today .num { font-weight: 800; }
.is-selected:not(.is-today) .mark::after { content: ""; position: absolute; inset: -4px -3px; border-radius: 1rem; border: 2px solid var(--color-primary); }
.is-selected.k-none .mark { background: var(--color-primary-soft); }
.day:focus-visible { outline-offset: -2px; }
@media (prefers-reduced-motion: no-preference) {
  .day:active .mark { transform: scale(0.94); transition: transform .12s; }
}
</style>
