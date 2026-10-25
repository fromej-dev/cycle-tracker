<template>
  <div>
    <ul class="group-list phase-period">
      <li
          v-for="period in visiblePeriods"
          :key="period.id"
          class="py-3.5 first:pt-0 last:pb-0 flex justify-between items-center gap-3"
      >
        <div class="flex items-center gap-3 min-w-0">
          <span class="phase-dot flex-shrink-0"></span>
          <div class="min-w-0">
            <p class="font-medium text-ink">
              {{ rangeText(period) }}
            </p>
            <p v-if="period.duration !== null" class="text-sm text-ink-soft">
              {{ $t('periodList.duration') }} {{ $t('common.dayN', period.duration) }}
            </p>
          </div>
        </div>
        <button
            @click="showDeleteConfirmation(period.id)"
            class="text-danger text-sm font-medium px-2 py-1 -mr-2 rounded-lg hover:bg-danger-soft transition-colors"
        >
          {{ $t('periodList.delete') }}
        </button>
      </li>
    </ul>
    <button v-if="periodsStore.periods.length > LIMIT" @click="expanded = !expanded" class="mt-4 w-full text-center text-sm font-semibold text-primary py-2 rounded-xl hover:bg-primary-soft transition-colors">
      {{ expanded ? $t('periodList.showLess') : $t('periodList.showAll', { n: periodsStore.periods.length }) }}
    </button>
    <div v-if="!periodsStore.periods.length && !periodsStore.loading" class="text-center text-ink-soft py-4">{{ $t('periodList.noPeriods') }}</div>

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
import { computed, onMounted, ref } from 'vue';
import { usePeriodsStore } from '@/stores/periods';
import { useReportsStore } from "@/stores/reports";
import { useToast } from '@/composables/useToast';
import { useI18n } from 'vue-i18n';
import { formatDay } from '@/utils/formatDate';
import ConfirmationModal from '@/components/ConfirmationModal.vue';

const periodsStore  = usePeriodsStore();
const reportStore = useReportsStore();
const toast = useToast();
const { t, locale } = useI18n();

const rangeText = (period) =>
  period.end_date
    ? `${formatDay(period.start_date, locale.value)}–${formatDay(period.end_date, locale.value)}`
    : `${formatDay(period.start_date, locale.value)} · ${t('periodList.ongoing')}`;

const LIMIT = 4;
const expanded = ref(false);
const visiblePeriods = computed(() => (expanded.value ? periodsStore.periods : periodsStore.periods.slice(0, LIMIT)));

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


