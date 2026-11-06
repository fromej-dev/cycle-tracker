<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ChevronLeftIcon, ArrowPathIcon } from '@heroicons/vue/24/outline';
import AdminApi from '@/api/admin';
import Skeleton from '@/components/Skeleton.vue';
import type { AdminStats } from '@/types';

const { t, locale } = useI18n();
const stats = ref<AdminStats | null>(null);
const loading = ref(true);
const error = ref<'forbidden' | 'failed' | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    stats.value = (await AdminApi.getStats()).data;
  } catch (e: any) {
    error.value = e?.response?.status === 403 ? 'forbidden' : 'failed';
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const nf = computed(() => new Intl.NumberFormat(locale.value));
const pct = computed(() => new Intl.NumberFormat(locale.value, { style: 'percent', maximumFractionDigits: 0 }));
const n = (v: number) => nf.value.format(v);
const share = (part: number, whole: number) => (whole ? pct.value.format(part / whole) : '—');

const userTiles = computed(() => {
  const u = stats.value?.users;
  if (!u) return [];
  return [
    { label: t('admin.users.total'), value: n(u.total) },
    { label: t('admin.users.active30'), value: n(u.active_30d), hint: share(u.active_30d, u.total) },
    { label: t('admin.users.new7'), value: n(u.new_7d) },
    { label: t('admin.users.new30'), value: n(u.new_30d) },
  ];
});

const months = computed(() => {
  const rows = stats.value?.signups_by_month ?? [];
  const max = Math.max(1, ...rows.map((r) => r.count));
  const fmt = new Intl.DateTimeFormat(locale.value, { month: 'short' });
  return rows.map((r) => {
    const [y, m] = r.month.split('-').map(Number);
    return { ...r, label: fmt.format(new Date(y, m - 1, 1)), height: (r.count / max) * 100 };
  });
});

const featureRows = computed(() => {
  const s = stats.value;
  if (!s) return [];
  const f = s.features;
  return (
    [
      ['periods', f.periods],
      ['symptoms', f.symptoms],
      ['plannedEvents', f.planned_events],
      ['calendarFeed', f.calendar_feed],
      ['partnerShare', f.partner_share],
      ['homeAssistant', f.home_assistant],
      ['webhooks', f.webhooks],
    ] as const
  ).map(([key, count]) => ({
    label: t(`admin.features.${key}`),
    count,
    ratio: s.users.total ? count / s.users.total : 0,
  }));
});

const dataRows = computed(() => {
  const d = stats.value?.data;
  if (!d) return [];
  return [
    { label: t('admin.data.periods'), value: n(d.periods) },
    { label: t('admin.data.ongoing'), value: n(d.ongoing_periods) },
    { label: t('admin.data.symptomDays'), value: n(d.symptom_days) },
    { label: t('admin.data.plannedEvents'), value: n(d.planned_events) },
    { label: t('admin.data.webhooks'), value: t('admin.data.webhooksValue', { total: n(d.webhooks), active: n(d.webhooks_active), off: n(d.webhooks_auto_disabled) }) },
  ];
});

const days = (v: number | null) => (v == null ? null : t('admin.cycles.days', { n: nf.value.format(v) }));
const generated = computed(() =>
  stats.value ? new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(stats.value.generated_at + 'Z')) : '',
);
</script>

<template>
  <div class="mx-auto max-w-2xl px-5 pt-7 pb-10 sm:px-8">
    <router-link :to="{ name: 'account' }" class="inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-primary">
      <ChevronLeftIcon class="h-4 w-4" />{{ $t('nav.account') }}
    </router-link>
    <header class="mt-1 flex items-start justify-between gap-4">
      <div>
        <h1 class="page-title">{{ $t('admin.title') }}</h1>
        <p class="mt-2 text-[0.9375rem] leading-snug text-ink-soft">{{ $t('admin.intro') }}</p>
      </div>
      <button type="button" class="btn btn-secondary shrink-0 !px-3" :disabled="loading" :aria-label="$t('admin.refresh')" @click="load">
        <ArrowPathIcon :class="['h-5 w-5', loading && 'animate-spin']" />
      </button>
    </header>

    <div v-if="error" class="card mt-6 p-6 text-ink-soft" role="alert">
      {{ error === 'forbidden' ? $t('admin.forbidden') : $t('admin.failed') }}
    </div>

    <div v-else-if="loading && !stats" class="mt-6 space-y-4">
      <Skeleton variant="card" />
      <Skeleton variant="card" />
      <Skeleton variant="rows" :rows="4" />
    </div>

    <div v-else-if="stats" class="mt-6 space-y-6">
      <!-- People -->
      <section aria-labelledby="admin-users" class="card p-6">
        <h2 id="admin-users" class="section-title mb-4">{{ $t('admin.users.title') }}</h2>
        <dl class="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div v-for="tile in userTiles" :key="tile.label" class="rounded-2xl bg-surface-muted p-4">
            <dt class="text-sm text-ink-soft">{{ tile.label }}</dt>
            <dd class="mt-1 font-display text-2xl text-ink tabular-nums">
              {{ tile.value }}<span v-if="tile.hint" class="ml-1.5 font-sans text-sm text-ink-soft">{{ tile.hint }}</span>
            </dd>
          </div>
        </dl>
        <p class="mt-3 text-xs text-ink-soft">{{ $t('admin.users.activeHint') }}</p>
      </section>

      <!-- Sign-ups per month -->
      <section aria-labelledby="admin-signups" class="card p-6">
        <h2 id="admin-signups" class="section-title mb-4">{{ $t('admin.signups.title') }}</h2>
        <div class="flex h-40 items-end gap-1.5" role="img" :aria-label="$t('admin.signups.aria')">
          <div v-for="m in months" :key="m.month" class="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
            <span class="text-xs tabular-nums text-ink-soft">{{ m.count || '' }}</span>
            <div class="w-full rounded-t-md bg-primary" :style="{ height: `max(${m.height}%, ${m.count ? '4px' : '1px'})`, opacity: m.count ? 1 : 0.25 }" :title="`${m.month}: ${m.count}`" />
          </div>
        </div>
        <div class="mt-1.5 flex gap-1.5">
          <span v-for="m in months" :key="m.month" class="min-w-0 flex-1 truncate text-center text-[0.6875rem] text-ink-soft">{{ m.label }}</span>
        </div>
      </section>

      <!-- Feature adoption -->
      <section aria-labelledby="admin-features" class="card p-6">
        <h2 id="admin-features" class="section-title mb-1">{{ $t('admin.features.title') }}</h2>
        <p class="mb-4 text-sm text-ink-soft">{{ $t('admin.features.hint') }}</p>
        <ul class="space-y-3">
          <li v-for="row in featureRows" :key="row.label">
            <div class="flex items-baseline justify-between gap-3 text-sm">
              <span class="text-ink">{{ row.label }}</span>
              <span class="tabular-nums text-ink-soft">{{ n(row.count) }} · {{ pct.format(row.ratio) }}</span>
            </div>
            <div class="mt-1 h-2 overflow-hidden rounded-full bg-surface-muted">
              <div class="h-full rounded-full bg-primary" :style="{ width: `${row.ratio * 100}%` }" />
            </div>
          </li>
        </ul>
      </section>

      <!-- Cycles (thresholded) -->
      <section aria-labelledby="admin-cycles" class="card p-6">
        <h2 id="admin-cycles" class="section-title mb-4">{{ $t('admin.cycles.title') }}</h2>
        <dl class="grid grid-cols-2 gap-4">
          <div class="rounded-2xl bg-surface-muted p-4">
            <dt class="text-sm text-ink-soft">{{ $t('admin.cycles.cycleLength') }}</dt>
            <dd class="mt-1 font-display text-2xl text-ink tabular-nums">{{ days(stats.cycles.median_cycle_length) ?? '—' }}</dd>
            <dd class="mt-1 text-xs text-ink-soft">{{ $t('admin.cycles.basedOn', { n: n(stats.cycles.users_with_cycles) }) }}</dd>
          </div>
          <div class="rounded-2xl bg-surface-muted p-4">
            <dt class="text-sm text-ink-soft">{{ $t('admin.cycles.periodLength') }}</dt>
            <dd class="mt-1 font-display text-2xl text-ink tabular-nums">{{ days(stats.cycles.median_period_length) ?? '—' }}</dd>
            <dd class="mt-1 text-xs text-ink-soft">{{ $t('admin.cycles.basedOn', { n: n(stats.cycles.users_with_period_length) }) }}</dd>
          </div>
        </dl>
        <p class="mt-3 text-xs text-ink-soft">{{ $t('admin.privacyThreshold', { n: stats.min_group_size }) }}</p>
      </section>

      <!-- Symptoms (thresholded, presets only) -->
      <section aria-labelledby="admin-symptoms" class="card p-6">
        <h2 id="admin-symptoms" class="section-title mb-1">{{ $t('admin.symptoms.title') }}</h2>
        <p class="mb-4 text-sm text-ink-soft">{{ $t('admin.symptoms.hint', { n: n(stats.symptoms.users_logging) }) }}</p>
        <ul v-if="stats.symptoms.top.length" class="space-y-3">
          <li v-for="s in stats.symptoms.top" :key="s.key">
            <div class="flex items-baseline justify-between gap-3 text-sm">
              <span class="text-ink">{{ $t(`symptoms.items.${s.key}`) }}</span>
              <span class="tabular-nums text-ink-soft">{{ pct.format(s.share) }}</span>
            </div>
            <div class="mt-1 h-2 overflow-hidden rounded-full bg-surface-muted">
              <div class="h-full rounded-full bg-primary" :style="{ width: `${s.share * 100}%` }" />
            </div>
          </li>
        </ul>
        <p v-else class="text-sm text-ink-soft">{{ $t('admin.notEnough', { n: stats.min_group_size }) }}</p>
      </section>

      <!-- Data volume -->
      <section aria-labelledby="admin-data" class="card p-6">
        <h2 id="admin-data" class="section-title mb-4">{{ $t('admin.data.title') }}</h2>
        <dl class="divide-y divide-line">
          <div v-for="row in dataRows" :key="row.label" class="flex items-baseline justify-between gap-4 py-2.5 text-sm">
            <dt class="text-ink-soft">{{ row.label }}</dt>
            <dd class="text-right tabular-nums text-ink">{{ row.value }}</dd>
          </div>
        </dl>
      </section>

      <p class="text-center text-xs text-ink-soft">{{ $t('admin.generated', { at: generated }) }}</p>
    </div>
  </div>
</template>
