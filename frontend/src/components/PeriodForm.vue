<script setup lang="ts">
import {ref, computed, onMounted} from 'vue';
import { usePeriodsStore } from '@/stores/periods';
import getTodayDateString from "@/utils/dateUtils.ts";
import { useI18n } from 'vue-i18n';
import { useToast } from '@/composables/useToast';

const { t } = useI18n();
const toast = useToast();

const periodsStore = usePeriodsStore();

const newPeriodStartDate = ref('');
const currentPeriodEndDate = ref('');

const currentOpenPeriod = computed(() => {
  const sortedPeriods = [...periodsStore.periods].sort((a, b) => new Date(b.start_date).getTime() - new Date(a.start_date).getTime());
  return sortedPeriods.find(period => !period.end_date);
});


const handleCreatePeriod = async () => {
  if (newPeriodStartDate.value) {
    await periodsStore.createPeriod(newPeriodStartDate.value);
    if (!periodsStore.error) {
      toast.success(t('toast.periodCreated'));
      newPeriodStartDate.value = getTodayDateString(); // Reset to today if needed
    } else {
      toast.error(periodsStore.error);
    }
  }
};

const handleUpdatePeriod = async () => {
  if (currentOpenPeriod.value && currentPeriodEndDate.value) {
    if (new Date(currentPeriodEndDate.value) < new Date(currentOpenPeriod.value.start_date)) {
      const errorMsg = t('periodForm.errors.endDateBeforeStart');
      periodsStore.setError(errorMsg);
      toast.error(errorMsg);
      return;
    }
    await periodsStore.updatePeriod(currentOpenPeriod.value.id, currentPeriodEndDate.value);
    if (!periodsStore.error) {
      toast.success(t('toast.periodUpdated'));
      currentPeriodEndDate.value = getTodayDateString(); // Reset to today if needed
    } else {
      toast.error(periodsStore.error);
    }
  }
};

onMounted(() => {
  // Initialize with today's date
  newPeriodStartDate.value = getTodayDateString();
  currentPeriodEndDate.value = getTodayDateString();

  // Fetch periods if needed, assuming it's done elsewhere or in the store constructor
  // periodsStore.fetchPeriods();
});
</script>

<template>
  <div class="space-y-6">
    <div>
      <h3 class="text-lg font-semibold text-primary mb-4">{{ $t('periodForm.recordNew.title') }}</h3>
      <div class="flex flex-col sm:flex-row sm:items-end sm:gap-4 space-y-3 sm:space-y-0">
        <div class="flex-grow">
          <label for="start_date" class="block text-sm font-medium text-gray-600 mb-1.5">{{ $t('periodForm.recordNew.startDateLabel') }}</label>
          <input
              type="date"
              id="start_date"
              v-model="newPeriodStartDate"
              class="block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary focus:ring focus:ring-primary focus:ring-opacity-50 py-2 px-3 text-gray-700 leading-tight"
              :max="getTodayDateString()"
          />
        </div>
        <button
            @click="handleCreatePeriod"
            :disabled="periodsStore.loading || !newPeriodStartDate"
            class="btn btn-primary"
        >
          {{ $t('periodForm.recordNew.button') }}
        </button>
      </div>
    </div>

    <div v-if="currentOpenPeriod" class="border-t border-gray-100 pt-6">
      <h3 class="text-lg font-semibold text-primary mb-4">{{ $t('periodForm.endCurrent.title') }}</h3>
      <p class="text-sm text-gray-600 mb-4">
        {{ $t('periodForm.endCurrent.startedOnPrefix') }}
        <span class="font-medium text-gray-700">{{ currentOpenPeriod.start_date }}</span>
      </p>
      <div class="flex flex-col sm:flex-row sm:items-end sm:gap-4 space-y-3 sm:space-y-0">
        <div class="flex-grow">
          <label for="end_date" class="block text-sm font-medium text-gray-600 mb-1.5">{{ $t('periodForm.endCurrent.endDateLabel') }}</label>
          <input
              type="date"
              id="end_date"
              v-model="currentPeriodEndDate"
              class="block w-full rounded-lg border-gray-300 shadow-sm focus:border-primary focus:ring focus:ring-primary focus:ring-opacity-50 py-2 px-3 text-gray-700 leading-tight"
              :min="currentOpenPeriod.start_date"
              :max="getTodayDateString()"
          />
        </div>
        <button
            @click="handleUpdatePeriod"
            :disabled="periodsStore.loading || !currentOpenPeriod || !currentPeriodEndDate"
            class="btn btn-primary"
        >
          {{ $t('periodForm.endCurrent.button') }}
        </button>
      </div>
    </div>

    <div v-if="periodsStore.error" class="mt-4 p-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md" role="alert">
      {{ periodsStore.error }}
    </div>
  </div>
</template>

<style scoped>
</style>
