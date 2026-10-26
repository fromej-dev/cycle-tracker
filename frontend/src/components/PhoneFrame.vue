<template>
  <div class="phone" :class="{ 'phone--eager': eager }">
    <img
        :src="src"
        :alt="alt"
        width="780"
        height="1688"
        :loading="eager ? 'eager' : 'lazy'"
        decoding="async"
        class="phone-screen"
    >
  </div>
</template>

<script setup lang="ts">
// A plain device bezel around a real app screenshot (780x1688, i.e. a 390x844 phone at 2x).
defineProps<{ src: string; alt: string; eager?: boolean }>()
</script>

<style scoped>
.phone {
  position: relative;
  border-radius: 2.75rem;
  padding: 0.55rem;
  background: #1d171f;
  box-shadow:
    0 0 0 1px rgb(255 255 255 / 0.06) inset,
    0 2px 4px rgb(43 32 41 / 0.08),
    0 30px 60px -20px rgb(43 32 41 / 0.35);
}
.phone-screen {
  display: block;
  width: 100%;
  height: auto;
  aspect-ratio: 780 / 1688;
  border-radius: 2.25rem;
  background: var(--color-background);
}
:global(.dark) .phone {
  background: #0c090d;
  box-shadow:
    0 0 0 1px rgb(255 255 255 / 0.1),
    0 30px 60px -20px rgb(0 0 0 / 0.7);
}
</style>
