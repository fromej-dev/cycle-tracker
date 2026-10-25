<script setup lang="ts">
import { ref } from 'vue';
import { ClipboardDocumentIcon, CheckIcon } from '@heroicons/vue/24/outline';
const props = defineProps<{ value: string; title: string; note: string; id: string }>();
const copied = ref(false);
async function copy() {
  try { await navigator.clipboard.writeText(props.value); }
  catch { const el = document.getElementById(props.id) as HTMLInputElement | null; el?.select(); document.execCommand?.('copy'); }
  copied.value = true; setTimeout(() => (copied.value = false), 2000);
}
</script>
<template>
  <div class="mb-5 rounded-2xl border border-line bg-surface-muted p-4">
    <p class="text-sm font-semibold">{{ title }}</p>
    <p class="mt-1 text-[0.8125rem] leading-snug text-ink-soft">{{ note }}</p>
    <div class="mt-3 flex items-center gap-2">
      <input :id="id" :value="value" readonly class="min-w-0 flex-1 !text-[0.8125rem]" aria-label="URL" @focus="($event.target as HTMLInputElement).select()" />
      <button type="button" class="btn btn-primary !min-h-11 !px-4 gap-1.5" @click="copy"><component :is="copied ? CheckIcon : ClipboardDocumentIcon" class="h-5 w-5" />{{ copied ? $t('feed.copied') : $t('feed.copy') }}</button>
    </div>
  </div>
</template>
