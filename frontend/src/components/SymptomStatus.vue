<script setup lang="ts">
/** One quiet line that says whether the day's symptoms are saved, with a retry when they are not. */
import { computed } from 'vue';
import { CheckIcon } from '@heroicons/vue/24/outline';
import { useSymptomsStore } from '@/stores/symptoms';

const props = defineProps<{ date: string }>();
const store = useSymptomsStore();
const status = computed(() => store.status[props.date]);
</script>

<template>
  <p class="min-h-5 text-[0.8125rem] leading-snug text-ink-soft" aria-live="polite">
    <span v-if="status === 'saving'">{{ $t('symptoms.status.saving') }}</span>
    <span v-else-if="status === 'saved'" class="inline-flex items-center gap-1"><CheckIcon class="h-4 w-4" aria-hidden="true" />{{ $t('symptoms.status.saved') }}</span>
    <span v-else-if="status === 'error'" class="text-danger-ink" role="alert">
      {{ $t('symptoms.status.error') }}
      <button type="button" class="ml-1 font-semibold underline underline-offset-2" @click="store.flush(date)">{{ $t('symptoms.status.retry') }}</button>
    </span>
    <span v-else>{{ $t('symptoms.status.auto') }}</span>
  </p>
</template>
