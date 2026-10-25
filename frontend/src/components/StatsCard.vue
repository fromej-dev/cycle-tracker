<template>
  <!-- A stat is a plain labelled figure; the grouping card lives in the parent -->
  <div class="stat">
    <div class="eyebrow">{{ title }}</div>
    <div class="mt-2 flex items-baseline gap-1.5">
      <span class="font-display text-title text-ink" style="font-variation-settings: 'SOFT' 80, 'opsz' 72; font-weight: 520">{{ value !== null && value !== undefined ? Number(value).toFixed(Number(decimals)) : '–' }}</span>
      <span v-if="unit" class="text-sm text-ink-soft">{{ unit }}</span>
    </div>
    <div class="text-ink-soft text-sm mt-1.5 leading-snug">{{ description }}</div>
  </div>
</template>

<script setup>
const props = defineProps({
  title: { type: String, required: true },
  value: { type: [Number, null], default: null },
  decimals: { type: [Number, String, null], default: 0 },
  unit: { type: String, default: '' },
  description: { type: String, default: '' }
});
</script>
