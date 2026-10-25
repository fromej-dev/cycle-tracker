<template>
  <div class="dashboard mx-auto max-w-5xl">

    <div v-if="reportsStore.loading && reportsStore.periodStats?.count === undefined" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      <p class="mt-4 text-ink-soft">{{ $t('dashboard.loader.message') }}</p>
    </div>

    <div v-else-if="reportsStore.error && reportsStore.periodStats?.count === undefined" class="bg-danger-soft border border-danger text-danger-ink p-6 m-4 rounded-3xl" role="alert">
      <p class="font-bold">{{ $t('dashboard.error.title') }}</p>
      <p>{{ reportsStore.error }} {{ $t('dashboard.error.refreshHint') }}</p>
    </div>

    <div v-else class="px-5 pt-6 pb-8 sm:px-8 flex flex-col gap-10">

      <TodayHero />

      <section v-if="reportsStore.periodStats?.count > 0" aria-labelledby="insights-heading" class="flex flex-col gap-4">
        <h2 id="insights-heading" class="section-title">{{ $t('dashboard.sections.insights.title') }}</h2>
        <div v-if="cycleHeadline !== '–' || periodHeadline !== '–'" class="grid grid-cols-2 items-end gap-6 border-y border-line py-5">
          <div v-if="cycleHeadline !== '–'">
            <p class="eyebrow">{{ $t('insights.cycle') }}</p>
            <p class="mt-2 font-display text-[1.625rem] leading-none whitespace-nowrap">{{ cycleHeadline }}</p>
          </div>
          <div v-if="periodHeadline !== '–'">
            <p class="eyebrow">{{ $t('insights.periodLength') }}</p>
            <p class="mt-2 font-display text-[1.625rem] leading-none whitespace-nowrap">{{ periodHeadline }}</p>
          </div>
        </div>
        <FertileWindowCard
            :fertile-start="reportsStore.cycleContext?.fertile_window?.start"
            :fertile-end="reportsStore.cycleContext?.fertile_window?.end"
            :ovulation-date="reportsStore.cycleContext?.ovulation_date"
            :is-today-ovulation="reportsStore.cycleContext?.is_today_ovulation"
            :is-in-fertile-window="reportsStore.cycleContext?.is_in_fertile_window"/>
      </section>

      <section id="record-period-section" class="grid grid-cols-1 lg:grid-cols-2 gap-10" aria-labelledby="log-history-heading">
        <div>
          <h2 id="log-history-heading" class="section-title mb-4">{{ $t('dashboard.sections.logHistory.recordTitle') }}</h2>
          <div class="card p-6">
            <PeriodForm />
          </div>
        </div>
        <div v-if="reportsStore.periodStats?.count > 0">
          <h2 class="section-title mb-4">{{ $t('dashboard.sections.logHistory.historyTitle') }}</h2>
          <div class="card p-6">
            <PeriodList/>
          </div>
        </div>
      </section>

    </div>
  </div>
</template>

<script setup>
import { useReportsStore } from '@/stores/reports';
import PeriodForm from '@/components/PeriodForm.vue';
import PeriodList from '@/components/PeriodList.vue';
import TodayHero from "@/components/TodayHero.vue";
import {computed, onMounted} from "vue";
import FertileWindowCard from "@/components/FertileWindowCard.vue";
import {usePeriodsStore} from "@/stores/periods";
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const reportsStore = useReportsStore();
const periodStore = usePeriodsStore();

const cycleHeadline = computed(() => {
  const avg = reportsStore.cycleContext?.cycle_length;
  const sd = reportsStore.forecast?.predictive_sd_days;
  if (!avg) return '–';
  const base = Math.round(avg);
  return sd != null && reportsStore.forecast?.cycles_used >= 3
    ? t('insights.cyclePlusMinus', { avg: base, sd: Math.max(1, Math.round(sd)) })
    : t('common.dayN', base);
});
const periodHeadline = computed(() => {
  const d = reportsStore.periodStats?.average_duration;
  return d ? t('common.dayN', Number(Number(d).toFixed(1))) : '–';
});

onMounted(async () => {
  // Fetch data - assuming fetch handles setting loading/error states
  reportsStore.fetchPeriodStats();
  reportsStore.fetchCycleContext();
  reportsStore.fetchForecast();
  periodStore.fetchPeriods();
})
</script>

<style scoped>
</style>
