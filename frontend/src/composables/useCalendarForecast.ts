import { computed, ref } from 'vue';
import { useReportsStore } from '@/stores/reports';

export interface DayProb {
  p_bleeding: number;
  p_fertile: number;
}

/**
 * Where the calendar gets its per-day probabilities. Today that is /reports/forecast (~45 days);
 * a Date Check response (any range, up to a year out) can be merged in with setExternalDays() and
 * takes precedence, without the calendar components changing.
 */
const external = ref<Record<string, Partial<DayProb>>>({});

export function setExternalDays(days: { date: string; p_bleeding?: number; p_fertile?: number }[]) {
  const next = { ...external.value };
  for (const d of days) next[d.date] = { p_bleeding: d.p_bleeding, p_fertile: d.p_fertile };
  external.value = next;
}

export function useCalendarForecast() {
  const reports = useReportsStore();
  const f = computed(() => reports.forecast);

  const isLate = computed(() => !!f.value && (f.value.is_late || f.value.confidence === 'overdue'));
  const hasDays = computed(() => !!f.value?.days?.length);
  /** no predictions at all: nothing to base them on (0/1 periods) or the period is overdue */
  const reason = computed<'learning' | 'late' | null>(() => {
    if (isLate.value) return 'late';
    if (!hasDays.value) return 'learning';
    return null;
  });

  const byDate = computed(() => {
    const m = new Map<string, DayProb>();
    if (reason.value) return m;
    for (const d of f.value?.days ?? []) m.set(d.date, { p_bleeding: d.p_bleeding, p_fertile: d.p_fertile });
    for (const [k, v] of Object.entries(external.value)) {
      const prev = m.get(k);
      m.set(k, { p_bleeding: v.p_bleeding ?? prev?.p_bleeding ?? 0, p_fertile: v.p_fertile ?? prev?.p_fertile ?? 0 });
    }
    return m;
  });

  const lastCovered = computed(() => {
    const ds = f.value?.days;
    return ds && ds.length ? ds[ds.length - 1].date : null;
  });
  const ovulation = computed(() => (reason.value ? null : f.value?.fertile_window?.ovulation_date ?? null));

  return { forecast: f, reason, isLate, byDate, lastCovered, ovulation, prob: (iso: string) => byDate.value.get(iso) ?? null };
}
