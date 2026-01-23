<template>
  <div>
    <ul class="space-y-4">
      <li
          v-for="period in periodsStore.periods"
          :key="period.id"
          class="bg-background p-4 rounded-lg shadow-sm border border-accent flex justify-between items-center hover:shadow-md transition-shadow"
      >
        <div>
          <p class="font-semibold text-text">
            {{ period.start_date }} - {{ period.end_date || $t('periodList.ongoing') }}
          </p>
          <p v-if="period.duration !== null" class="text-sm text-gray-600 dark:text-gray-400">
            {{ $t('periodList.duration') }} {{ $t('common.dayN', period.duration) }}
          </p>
        </div>
        <div>
          <button
              @click="showDeleteConfirmation(period.id)"
              class="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 text-sm font-medium transition-colors"
          >
            {{ $t('periodList.delete') }}
          </button>
        </div>
      </li>
    </ul>
    <div v-if="!periodsStore.periods.length && !periodsStore.loading" class="text-center text-gray-500 dark:text-gray-400">{{ $t('periodList.noPeriods') }}</div>

    <!-- Delete Confirmation Modal -->
    <ConfirmationModal
      v-model="showDeleteModal"
      :title="$t('periodList.confirmDelete.title')"
      :message="$t('periodList.confirmDelete.message')"
      :confirmText="$t('periodList.confirmDelete.confirm')"
      :cancelText="$t('periodList.confirmDelete.cancel')"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { usePeriodsStore } from '@/stores/periods';
import { useReportsStore } from "@/stores/reports";
import { useToast } from '@/composables/useToast';
import { useI18n } from 'vue-i18n';
import ConfirmationModal from '@/components/ConfirmationModal.vue';

const periodsStore  = usePeriodsStore();
const reportStore = useReportsStore();
const toast = useToast();
const { t } = useI18n();

const showDeleteModal = ref(false);
const periodToDelete = ref(null);

const showDeleteConfirmation = (periodId) => {
  periodToDelete.value = periodId;
  showDeleteModal.value = true;
};

const confirmDelete = async () => {
  if (periodToDelete.value === null) return;

  await periodsStore.deletePeriod(periodToDelete.value);

  if (!periodsStore.error) {
    toast.success(t('toast.periodDeleted'));
    await reportStore.fetchCycleContext();
  } else {
    toast.error(periodsStore.error);
  }

  showDeleteModal.value = false;
  periodToDelete.value = null;
};

onMounted(async () => {
  await periodsStore.fetchPeriods()
})
</script>

<style scoped>
/* PeriodList specific styles */
</style>
