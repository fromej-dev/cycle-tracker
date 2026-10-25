import { computed, ref } from 'vue';
import { addDays, differenceInCalendarDays, formatISO, parseISO } from 'date-fns';
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

const externalCovered = ref<string | null>(null);

export function setExternalDays(days: { date: string; p_bleeding?: number; p_fertile?: number }[]) {
  const next = { ...external.value };
  for (const d of days) {
    next[d.date] = { p_bleeding: d.p_bleeding, p_fertile: d.p_fertile };
    if (!externalCovered.value || d.date > externalCovered.value) externalCovered.value = d.date;
  }
  external.value = next;
}
/** The forecast changed (a period was logged): longer-range days fetched earlier are stale. */
export function clearExternalDays() { external.value = {}; externalCovered.value = null; }

export interface FertileDay {
  /** 0..1, how central the day is to the window (peak on the ovulation day) */
  strength: number;
  ovulation: boolean;
  /** next cycle's window, extrapolated from the forecast rather than computed by it */
  projected: boolean;
}

const iso = (d: Date) => formatISO(d, { representation: 'date' });

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

  /** last day the /forecast itself covers */
  const forecastEnd = computed(() => {
    const ds = f.value?.days;
    return ds && ds.length ? ds[ds.length - 1].date : null;
  });
  const lastCovered = computed(() => {
    const a = forecastEnd.value, b = externalCovered.value;
    return a && b ? (a > b ? a : b) : a ?? b;
  });
  const ovulation = computed(() => (reason.value ? null : f.value?.fertile_window?.ovulation_date ?? null));

  // The fertile window is ONE continuous band from fertile_window.start to .end (= ovulation + 1), whole days,
  // past ones included. It is the same window the Today ring draws. p_fertile is deliberately not used for
  // membership: its tails leak past ovulation, where conception is impossible.
  const fertileMap = computed(() => {
    const m = new Map<string, FertileDay>();
    const fw = f.value?.fertile_window;
    if (reason.value || !fw?.start || !fw.end || !fw.ovulation_date) return m;
    const put = (start: Date, end: Date, ov: Date, projected: boolean) => {
      const n = differenceInCalendarDays(end, start);
      for (let i = 0; i <= n; i++) {
        const d = addDays(start, i);
        const dist = Math.abs(differenceInCalendarDays(d, ov));
        const k = dist === 0 ? 1 : Math.max(0.4, 1 - 0.14 * dist);
        m.set(iso(d), { strength: projected ? k * 0.65 : k, ovulation: dist === 0, projected });
      }
    };
    const s0 = parseISO(fw.start), e0 = parseISO(fw.end), o0 = parseISO(fw.ovulation_date);
    put(s0, e0, o0, false);
    // next cycle: same geometry relative to ovulation, one (typical) cycle later
    const len = Math.round((reports.cycleContext as any)?.cycle_length ?? 0);
    if (len >= 20 && len <= 45) put(addDays(s0, len), addDays(e0, len), addDays(o0, len), true);
    return m;
  });

  return { fertileMap, forecastEnd, forecast: f, reason, isLate, byDate, lastCovered, ovulation, prob: (iso: string) => byDate.value.get(iso) ?? null };
}
