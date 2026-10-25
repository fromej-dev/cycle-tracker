<script setup lang="ts">
import { useReportsStore } from '@/stores/reports';
import { computed } from 'vue';
import { differenceInDays, parseISO, isValid, startOfDay, subDays } from 'date-fns';
import { SparklesIcon } from '@heroicons/vue/24/solid';
import { useI18n } from 'vue-i18n';

const store = useReportsStore();
const { t } = useI18n();

// --- Date and Phase Calculations ---
const currentDate = computed(() => startOfDay(new Date()));

const cycleStartDate = computed(() => {
  // Calculate start date based on current date and cycle day
  if (store.cycleContext?.cycle_day) {
    try {
      // Subtract (cycle_day - 1) days from today
      return subDays(currentDate.value, store.cycleContext.cycle_day - 1);
    } catch (e) {
      console.error("Error calculating cycle start date:", e);
    }
  }
  return null;
});

const getDayNumber = (dateStr: string | null): number | null => {
  // Helper to calculate day number within the cycle from a date string
  if (!dateStr || !cycleStartDate.value) return null;
  try {
    const date = parseISO(dateStr);
    const startDate = cycleStartDate.value;
    if (isValid(date) && isValid(startDate)) {
      const dayNum = differenceInDays(date, startDate) + 1;
      return dayNum > 0 ? dayNum : null; // Return null if date is before start date
    }
  } catch (e) {
    console.error(`Error calculating day number for ${dateStr}:`, e);
  }
  return null;
};

const ovulationDayNumber = computed(() => getDayNumber(store.cycleContext?.ovulation_date));
const fertileStartDayNumber = computed(() => getDayNumber(store.cycleContext?.fertile_window?.start));
const fertileEndDayNumber = computed(() => getDayNumber(store.cycleContext?.fertile_window?.end));

const getPercent = (dayNumber: number | null): number | null => {
  // Helper to calculate percentage position
  const cycleLength = store.cycleContext?.cycle_length;
  if (dayNumber !== null && cycleLength && cycleLength > 0) {
    const percent = (dayNumber / cycleLength) * 100;
    return Math.max(0, Math.min(100, percent));
  }
  return null;
};

const ovulationPercent = computed(() => getPercent(ovulationDayNumber.value));
const fertileStartPercent = computed(() => getPercent(fertileStartDayNumber.value));
const fertileEndPercent = computed(() => getPercent(fertileEndDayNumber.value));

const fertileWindowWidthPercent = computed(() => {
  if (fertileStartPercent.value !== null && fertileEndPercent.value !== null) {
    // Calculate width, add small buffer for end day inclusivity visual
    const width = fertileEndPercent.value - fertileStartPercent.value;
    const oneDayWidth = store.cycleContext?.cycle_length ? (1 / store.cycleContext.cycle_length) * 100 : 0;
    return Math.max(0, width + (oneDayWidth / 2)); // Make slightly wider to feel inclusive of end day
  }
  return 0;
});

const cycleLengthDisplay = computed(() => store.cycleContext?.cycle_length ?? '~');
const progressPercentDisplay = computed(() => store.cycleContext?.progress_percent ?? 0);

// --- End Calculations ---

</script>

<template>
  <div class="card phase-fertile p-5">
    <div v-if="!store.cycleContext" class="space-y-3 animate-pulse">
      <div class="flex justify-between items-center">
        <div class="h-4 bg-surface-muted rounded w-2/5"></div>
        <div class="h-4 bg-surface-muted rounded w-1/4"></div>
      </div>
      <div class="relative pt-1 pb-3">
        <div class="h-2.5 bg-surface-muted rounded-full w-full"></div>
      </div>
      <div class="flex justify-between">
        <div class="h-3 bg-surface-muted rounded w-1/12"></div>
        <div class="h-3 bg-surface-muted rounded w-1/12"></div>
      </div>
    </div>

    <div v-else class="space-y-2">
      <div class="flex justify-between items-center gap-2">
        <span class="text-sm font-semibold text-ink flex-shrink-0">
          {{ t('cycleProgressBar.title.dayOf', [store.cycleContext.cycle_day, cycleLengthDisplay]) }}
        </span>
        <span v-if="store.cycleContext.days_until_next_period !== null" class="text-sm text-ink-soft text-right flex-shrink overflow-hidden whitespace-nowrap text-ellipsis">
          {{ t('cycleProgressBar.title.remaining', store.cycleContext.days_until_next_period) }}
        </span>
      </div>

      <div class="relative pt-1 pb-4">
        <div class="relative w-full h-3 bg-surface-muted rounded-full overflow-hidden">
          <div
              v-if="fertileStartPercent !== null && fertileWindowWidthPercent > 0"
              class="absolute top-0 bottom-0 h-full rounded-md is-predicted"
              :style="{ left: `${fertileStartPercent}%`, width: `${fertileWindowWidthPercent}%` }"
              :title="t('cycleProgressBar.tooltips.fertileWindow')"
          ></div>
          <div
              class="absolute top-0 bottom-0 left-0 h-full bg-primary rounded-full transition-all duration-500 ease-out z-10"
              :style="{ width: `${progressPercentDisplay}%` }"
          />
        </div>

        <div
            v-if="ovulationPercent !== null"
            class="absolute bottom-0 transform -translate-x-1/2 translate-y-[calc(50%+1px)] z-20"
            :style="{ left: `${ovulationPercent}%` }"
            :title="t('cycleProgressBar.tooltips.ovulationPrefix', ovulationDayNumber)"
        >
          <SparklesIcon class="h-3.5 w-3.5 text-fertile" aria-hidden="true" />
        </div>
      </div>

      <div class="relative flex justify-between text-xs text-ink-soft h-4">
        <span>{{ t('cycleProgressBar.labels.start') }}</span>

        <span
            v-if="ovulationPercent !== null && ovulationDayNumber"
            class="absolute transform -translate-x-1/2 text-fertile-ink font-medium whitespace-nowrap"
            :style="{ left: `${ovulationPercent}%` }"
        >
            {{ t('cycleProgressBar.labels.ovulation') }}
        </span>

        <span>{{ t('cycleProgressBar.labels.end', {number: cycleLengthDisplay})}}</span>
      </div>

    </div>
  </div>
</template>

<style scoped>
</style>
