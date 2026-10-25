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
  pFertile?: number;
  ovulation?: boolean;
  today?: boolean;
  selected?: boolean;
  future?: boolean;
  label?: string;
}
const props = withDefaults(defineProps<Props>(), { pBleeding: 0, pFertile: 0 });

const MIN = 0.04;
const kind = computed(() => {
  if (props.logged) return 'logged';
  if (props.pBleeding >= MIN) return 'predicted';
  if (props.pFertile >= 0.08) return 'fertile';
  return 'none';
});
const strength = computed(() => {
  const p = kind.value === 'predicted' ? props.pBleeding : props.pFertile;
  return Math.min(1, Math.sqrt(Math.max(0, p)));
});
const style = computed(() => ({ '--s': strength.value.toFixed(3) }));
</script>

<template>
  <button
      type="button"
      class="day"
      :class="[`k-${kind}`, { 'join-prev': joinPrev && logged, 'join-next': joinNext && logged, 'is-today': today, 'is-selected': selected }]"
      :style="style"
      :aria-label="label"
      :aria-pressed="selected"
      :aria-current="today ? 'date' : undefined"
  >
    <span class="mark" aria-hidden="true"></span>
    <span v-if="today" class="today-ring" aria-hidden="true"></span>
    <span class="num">{{ day }}</span>
    <span v-if="ovulation" class="ov" aria-hidden="true"></span>
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

.k-predicted .mark {
  background: color-mix(in srgb, var(--color-period) calc(7% + 30% * var(--s)), var(--color-surface));
  border: 1.5px dashed color-mix(in srgb, var(--color-period) calc(35% + 55% * var(--s)), transparent);
}
.k-fertile .mark {
  background: color-mix(in srgb, var(--color-fertile) calc(10% + 30% * var(--s)), var(--color-surface));
}
.ov { position: absolute; z-index: 2; bottom: 0.4rem; width: 0.3125rem; height: 0.3125rem; border-radius: 9999px; background: var(--color-fertile); box-shadow: 0 0 0 1.5px var(--color-surface); }

.today-ring { position: absolute; inset: 0.125rem 0.0625rem; border-radius: 1rem; border: 2px solid var(--color-ink); z-index: 1; }
.is-today .num { font-weight: 800; }
.is-selected:not(.is-today) .mark::after { content: ""; position: absolute; inset: -4px -3px; border-radius: 1rem; border: 2px solid var(--color-primary); }
.is-selected.k-none .mark { background: var(--color-primary-soft); }
.day:focus-visible { outline-offset: -2px; }
@media (prefers-reduced-motion: no-preference) {
  .day:active .mark { transform: scale(0.94); transition: transform .12s; }
}
</style>
