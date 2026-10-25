<template>
  <div class="card p-6 flex flex-col gap-6">
    <div v-if="activePeriod?.end_date === null" class="phase-period">
      <p class="eyebrow">{{ $t('statusCard.eyebrowPeriod') }}</p>
      <p class="mt-3 flex items-baseline gap-2">
        <span class="display-number text-period-ink">{{ reportStore.cycleContext?.days_running }}</span>
        <span class="font-display text-heading text-ink-soft">{{ $t('common.day', reportStore.cycleContext?.days_running) }} {{ $t('statusCard.mainText.daysOngoing') }}</span>
      </p>
      <p v-if="startedLabel" class="mt-3 text-sm text-ink-soft">{{ $t('statusCard.periodStarted') }} {{ startedLabel }}</p>
    </div>

    <div v-else-if="reportStore.cycleContext?.days_until_next_period !== null && reportStore.cycleContext?.days_until_next_period !== undefined">
      <template v-if="reportStore.cycleContext.days_until_next_period > 0">
        <p class="flex items-baseline gap-2.5">
          <span class="display-number">{{ reportStore.cycleContext.days_until_next_period }}</span>
          <span class="font-display text-heading text-ink-soft">{{ $t('common.day', reportStore.cycleContext.days_until_next_period) }}</span>
        </p>
        <p class="mt-2 text-ink-soft">{{ $t('statusCard.subtitle.daysLeft') }}</p>
      </template>
      <template v-else-if="reportStore.cycleContext.days_until_next_period === 0">
        <p class="eyebrow">{{ $t('statusCard.eyebrowNext') }}</p>
        <p class="mt-3 display-number">{{ $t('statusCard.subtitle.dueToday') }}</p>
      </template>
      <template v-else>
        <p class="eyebrow">{{ $t('statusCard.eyebrowLate') }}</p>
        <p class="mt-3 flex items-baseline gap-2.5">
          <span class="display-number text-period-ink">{{ Math.abs(reportStore.cycleContext.days_until_next_period) }}</span>
          <span class="font-display text-heading text-ink-soft">{{ $t('common.day', Math.abs(reportStore.cycleContext.days_until_next_period)) }}</span>
        </p>
        <p class="mt-2 font-medium text-period-ink">{{ $t('statusCard.subtitle.overdue') }}</p>
      </template>
      <p class="phase-period mt-4 inline-flex items-center gap-2 text-xs text-ink-soft">
        <span class="phase-chip is-predicted !py-0.5">{{ $t('phases.predicted') }}</span>
        {{ $t('statusCard.predictedHint') }}
      </p>
    </div>

    <p v-else class="display-number">{{ $t('common.notAvailable') }}</p>

    <button @click="handlePeriodCardClick" class="btn btn-primary w-full">
      {{ buttonText }}
    </button>
  </div>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from 'vue';
import { usePeriodsStore } from '@/stores/periods';
import { useReportsStore } from '@/stores/reports';
import { formatISO } from 'date-fns';
import { Period } from "@/types.ts";
import PeriodApi from "@/api/periods.ts";
import { useI18n } from 'vue-i18n';
import { formatDay } from '@/utils/formatDate';

const { t, locale } = useI18n();
const periodsStore = usePeriodsStore();
const reportStore = useReportsStore();

const activePeriod = ref<Period | null>(null)

const startedLabel = computed(() => formatDay(activePeriod.value?.start_date, locale.value));

const today = formatISO(new Date(), { representation: 'date' });

const buttonText = computed(() => {
  return activePeriod.value?.end_date === null ? t("periodForm.endCurrent.button") : t("periodForm.recordNew.button");
})

const handlePeriodCardClick = async () => {
  if (!activePeriod.value?.start_date) {
    activePeriod.value = await periodsStore.createPeriod(today);
  } else {
    activePeriod.value = await periodsStore.updatePeriod(activePeriod.value.id, today);
  }
};

onMounted(async () =>{
  try{
    const response = await PeriodApi.getActivePeriod()
    activePeriod.value = response.data
  } catch (error) {
    console.log(error);
    activePeriod.value = null
  }
})

</script>
