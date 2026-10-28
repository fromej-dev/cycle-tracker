import { defineStore } from 'pinia';
import { symptomsApi, type SymptomDay, type SymptomSuggestions } from '@/api/symptoms';
import { SYMPTOM_KEYS, CUSTOM_MAX_LEN, CUSTOM_MAX_PER_DAY } from '@/utils/symptoms';

type Status = 'saving' | 'saved' | 'error';
const SAVE_DELAY = 600;
const timers = new Map<string, number>();
const fetched = new Set<string>();

/**
 * Symptoms per day. Every tap changes the local copy at once and saves it a moment later
 * (several quick taps become one request), so there is never a save button to forget.
 */
export const useSymptomsStore = defineStore('symptoms', {
  state: () => ({
    byDate: {} as Record<string, SymptomDay>,
    status: {} as Record<string, Status>,
    suggestions: { frequent: [], recent_custom: [] } as SymptomSuggestions,
  }),

  getters: {
    day: (state) => (date: string): SymptomDay => state.byDate[date] ?? { date, symptoms: [], custom: [] },
    count: (state) => (date: string) => {
      const d = state.byDate[date];
      return d ? d.symptoms.length + d.custom.length : 0;
    },
  },

  actions: {
    /** Forget everything (logout): another account must never see these days. */
    reset() {
      for (const t of timers.values()) clearTimeout(t);
      timers.clear();
      fetched.clear();
      this.$reset();
    },
    async fetchRange(start: string, end: string) {
      const key = `${start}/${end}`;
      if (fetched.has(key)) return;
      fetched.add(key);
      try {
        const r = await symptomsApi.range(start, end);
        // never overwrite a day that has unsaved taps
        for (const d of r.data) if (!timers.has(d.date) && this.status[d.date] !== 'saving') this.byDate[d.date] = d;
      } catch { fetched.delete(key); }
    },
    async fetchSuggestions() {
      try { this.suggestions = (await symptomsApi.suggestions()).data; } catch { /* the defaults still work */ }
    },

    edit(date: string, fn: (d: SymptomDay) => void) {
      const d = this.day(date);
      const next = { date, symptoms: [...d.symptoms], custom: [...d.custom] };
      fn(next);
      next.symptoms = SYMPTOM_KEYS.filter((k) => next.symptoms.includes(k));
      this.byDate[date] = next;
      this.schedule(date);
    },
    toggle(date: string, key: string) {
      this.edit(date, (d) => {
        d.symptoms = d.symptoms.includes(key) ? d.symptoms.filter((k) => k !== key) : [...d.symptoms, key];
      });
    },
    /** Adds (or, when already there, keeps) an own symptom. Returns false when it cannot be added. */
    addCustom(date: string, raw: string): boolean {
      const label = raw.replace(/\s+/g, ' ').trim();
      if (!label || label.length > CUSTOM_MAX_LEN) return false;
      const d = this.day(date);
      if (d.custom.some((c) => c.toLowerCase() === label.toLowerCase())) return true;
      if (d.custom.length >= CUSTOM_MAX_PER_DAY) return false;
      this.edit(date, (x) => { x.custom = [...x.custom, label]; });
      return true;
    },
    removeCustom(date: string, label: string) {
      this.edit(date, (d) => { d.custom = d.custom.filter((c) => c !== label); });
    },
    toggleCustom(date: string, label: string) {
      if (this.day(date).custom.includes(label)) this.removeCustom(date, label);
      else this.addCustom(date, label);
    },

    schedule(date: string) {
      const t = timers.get(date);
      if (t) clearTimeout(t);
      this.status[date] = 'saving';
      timers.set(date, window.setTimeout(() => this.flush(date), SAVE_DELAY));
    },
    /** Save now: one day, or every day with pending taps (e.g. when a sheet closes). */
    async flush(date?: string) {
      const dates = date ? [date] : [...timers.keys()];
      await Promise.all(dates.map(async (d) => {
        const t = timers.get(d);
        if (t) clearTimeout(t);
        timers.delete(d);
        const entry = this.day(d);
        const sent = JSON.stringify(entry);
        this.status[d] = 'saving';
        try {
          const r = await symptomsApi.save(d, { symptoms: entry.symptoms, custom: entry.custom });
          // a newer tap may have come in while this request was on its way: keep that one
          if (JSON.stringify(this.day(d)) === sent) {
            this.byDate[d] = r.data;
            this.status[d] = 'saved';
          }
          const recent = this.suggestions.recent_custom;
          const fresh = r.data.custom.filter((c) => !recent.some((x) => x.toLowerCase() === c.toLowerCase()));
          if (fresh.length) this.suggestions.recent_custom = [...fresh, ...recent].slice(0, 12);
        } catch {
          if (!timers.has(d)) this.status[d] = 'error';
        }
      }));
    },
  },
});
