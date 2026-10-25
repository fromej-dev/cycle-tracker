<template>
  <div class="card phase-fertile p-6 flex flex-col justify-between">
    <div>
      <div class="flex items-start justify-between mb-3">
        <div class="flex items-center space-x-2">
          <component :is="statusIcon.icon" :class="['h-6 w-6 flex-shrink-0', statusIcon.colorClass]" aria-hidden="true" />
          <h2 class="section-title" id="fertility-card-title">
            {{ $t('fertileWindowCard.title') }}
          </h2>
        </div>
        <span
            class="phase-chip"
            :class="statusBadgeClass"
        >
          {{ statusLabel }}
        </span>
      </div>
      <div class="mt-1 mb-2 text-ink leading-relaxed">
        <i18n-t keypath="fertileWindowCard.statusText.ovulation" tag="p" v-if="isTodayOvulation">
          <template #emphasis>
            <b>{{ $t('fertileWindowCard.statusEmphasis.ovulation') }}</b>
          </template>
        </i18n-t>
        <i18n-t keypath="fertileWindowCard.statusText.fertile" tag="p" v-else-if="isInFertileWindow">
          <template #emphasis>
            <b>{{ $t('fertileWindowCard.statusEmphasis.fertile') }}</b>
          </template>
        </i18n-t>
        <i18n-t keypath="fertileWindowCard.statusText.low" tag="p" v-else-if="fertileStart">
          <template #emphasis>
            <b>{{ $t('fertileWindowCard.statusEmphasis.low') }}</b>
          </template>
        </i18n-t>
        <i18n-t keypath="fertileWindowCard.statusText.unknown" tag="p" v-else>
          <template #emphasis>
            <b>{{ $t('fertileWindowCard.statusEmphasis.unknown') }}</b>
          </template>
        </i18n-t>
      </div>
    </div>

    <div class="mt-4 text-sm border-t border-line pt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
      <span class="text-ink-soft">{{ $t('fertileWindowCard.dateLabels.fertileWindow') }}</span>
      <span class="text-ink font-medium text-right">{{ rangeLabel }}</span>
      <span class="text-ink-soft">{{ $t('fertileWindowCard.dateLabels.ovulation') }}</span>
      <span class="text-ink font-medium text-right">{{ ovulationLabel }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { formatDay, formatRange } from '@/utils/formatDate';
import { SparklesIcon, SunIcon, CheckCircleIcon, InformationCircleIcon } from '@heroicons/vue/24/outline';
import { useI18n } from 'vue-i18n';

const { t, locale } = useI18n();

const props = defineProps<{
  fertileStart: string | null;
  fertileEnd: string | null;
  ovulationDate: string | null;
  isTodayOvulation: boolean;
  isInFertileWindow: boolean;
}>();

const rangeLabel = computed(() => formatRange(props.fertileStart, props.fertileEnd, locale.value) ?? t('common.notAvailable'));
const ovulationLabel = computed(() => formatDay(props.ovulationDate, locale.value) ?? t('common.notAvailable'));

// Status Logic for Labels, Icons, and Badges
const statusInfo = computed(() => {
  if (props.isTodayOvulation) {
    return {
      label: t('fertileWindowCard.statusLabels.ovulation'),
      icon: SparklesIcon,
      iconColorClass: 'text-fertile',
      badgeClass: '!bg-fertile !text-on-phase',
    };
  }
  if (props.isInFertileWindow) {
    return {
      label: t('fertileWindowCard.statusLabels.fertile'),
      icon: SunIcon,
      iconColorClass: 'text-fertile',
      badgeClass: '',
    };
  }
  if (props.fertileStart && props.fertileEnd && props.ovulationDate) {
    return {
      label: t('fertileWindowCard.statusLabels.low'),
          icon: CheckCircleIcon,
        iconColorClass: 'text-ink-soft',
        badgeClass: 'bg-surface-muted text-ink-soft ring-1 ring-inset ring-line',
    };
  }
  return {
    label: t('fertileWindowCard.statusLabels.unknown'),
    icon: InformationCircleIcon,
    iconColorClass: 'text-ink-soft',
    badgeClass: 'bg-surface-muted text-ink-soft ring-1 ring-inset ring-line',
  };
});

const statusLabel = computed(() => statusInfo.value.label);
const statusIcon = computed(() => ({ icon: statusInfo.value.icon, colorClass: statusInfo.value.iconColorClass }));
const statusBadgeClass = computed(() => statusInfo.value.badgeClass);

</script>


