<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { addDays, differenceInCalendarDays, formatISO, parseISO, isValid } from 'date-fns';
import { BookmarkIcon, PencilSquareIcon } from '@heroicons/vue/24/outline';
import BottomSheet from '@/components/BottomSheet.vue';
import DateField from '@/components/DateField.vue';
import { useReportsStore } from '@/stores/reports';
import Skeleton from '@/components/Skeleton.vue';
import { dateCheckApi, eventsApi, apiMessage, localToday, type DateCheck, type PlanEvent } from '@/api/plan';
import { formatRange, formatDay, formatBetween } from '@/utils/formatDate';
import { useToast } from '@/composables/useToast';

const { t, te, locale } = useI18n();
const toast = useToast();
const reports = useReportsStore();
// One rule for solid vs dashed bars: solid when the chance of bleeding that day is at least 50%.
const SOLID_AT = 0.5;
const startConf = 80;
// the 80% window for the period START, drawn as an underline under the bars (like the calendar's underline)
const startWin = computed(() => {
  const r = reports.forecast?.interval_80;
  return r ?? null;
});
const startNote = computed(() => {
  const r = reports.forecast?.interval_80;
  const bt = formatBetween(r?.start, r?.end, locale.value);
  if (!bt) return '';
  return t('plan.startNote', { pct: startConf, range: r!.start === r!.end ? bt.b : `${bt.a}–${bt.b}` });
});
const iso = (d: Date) => formatISO(d, { representation: 'date' });
const todayISO = localToday();

const start = ref(iso(addDays(parseISO(todayISO), 10)));
const end = ref(iso(addDays(parseISO(todayISO), 16)));
const result = ref<DateCheck | null>(null);
const checking = ref(false);
const formError = ref<string | null>(null);
const apiError = ref<string | null>(null);

const nDays = computed(() => (start.value && end.value ? differenceInCalendarDays(parseISO(end.value), parseISO(start.value)) + 1 : 0));
const maxEnd = computed(() => (start.value ? iso(addDays(parseISO(start.value), 59)) : undefined));
const maxAhead = iso(addDays(parseISO(todayISO), 366));

function validate(): string | null {
  if (!start.value || !end.value) return t('plan.errors.pick');
  if (!isValid(parseISO(start.value)) || !isValid(parseISO(end.value))) return t('plan.errors.pick');
  if (nDays.value < 1) return t('plan.errors.order');
  if (nDays.value > 60) return t('plan.errors.tooLong');
  if (end.value > maxAhead) return t('plan.errors.tooFar');
  return null;
}

let seq = 0;
let timer: number | undefined;
async function check() {
  formError.value = validate();
  apiError.value = null;
  if (formError.value) { result.value = null; return; }
  const my = ++seq;
  checking.value = true;
  try {
    const r = await dateCheckApi.check(start.value, end.value);
    if (my === seq) result.value = r.data;
  } catch (e: any) {
    if (my === seq) { result.value = null; apiError.value = apiMessage(e, t('plan.errors.generic')); }
  } finally { if (my === seq) checking.value = false; }
}
function onStart() {
  if (start.value && (!end.value || end.value < start.value)) end.value = start.value;
}
watch([start, end], () => { clearTimeout(timer); timer = window.setTimeout(check, 250); });

// ---- the answer ----
const ok = computed(() => result.value?.status === 'ok' && result.value.probability_any !== null);
const pct = computed(() => {
  const p = result.value?.probability_any ?? 0;
  return p < 0.01 ? '<1' : p > 0.99 ? '>99' : String(Math.round(p * 100));
});
const single = computed(() => start.value === end.value);
const rangeText = computed(() => formatRange(start.value, end.value, locale.value) ?? '');
const answerSentence = computed(() => (single.value
  ? t('plan.answer.single', { date: formatDay(start.value, locale.value) })
  : t('plan.answer.range', { n: nDays.value })));

const cells = computed(() => {
  const days = result.value?.days ?? [];
  const max = Math.max(0.05, ...days.map((d) => d.p_bleeding));
  return days.map((d) => ({
    date: d.date,
    day: parseISO(d.date).getDate(),
    p: d.p_bleeding,
    h: Math.max(8, Math.round((d.p_bleeding / max) * 100)),
    likely: d.p_bleeding >= SOLID_AT,
    inWin: !!startWin.value && d.date >= startWin.value.start && d.date <= startWin.value.end,
    pct: d.p_bleeding < 0.005 ? '' : d.p_bleeding < 0.01 ? '<1%' : Math.round(d.p_bleeding * 100) + '%',
    label: `${formatDay(d.date, locale.value)}: ${Math.round(d.p_bleeding * 100)}%`,
  }));
});
// first/last column (1-based grid lines) of the start window inside the chosen days
const winSpan = computed(() => {
  const idx = cells.value.map((c, i) => (c.inWin ? i : -1)).filter((i) => i >= 0);
  return idx.length ? { from: idx[0] + 1, to: idx[idx.length - 1] + 2 } : null;
});
const higherThanStart = computed(() => !!startNote.value && !!winSpan.value && (result.value?.probability_any ?? 0) * 100 > startConf);
const tickEvery = computed(() => (cells.value.length <= 14 ? 1 : 7));

// the API answers in English sentences: show them as they are in English, a generic line of our own otherwise
const isNl = computed(() => locale.value.startsWith('nl'));
const mapped = (prefix: string, v: string | null) => {
  if (!v) return null;
  if (te(`${prefix}.${v}`)) return t(`${prefix}.${v}`);
  if (!isNl.value) return v;
  return prefix === 'plan.horizons' ? t('plan.horizonGeneric') : t('plan.reasonGeneric');
};
const reasonText = computed(() => mapped('plan.reasons', result.value?.reason ?? null));
const horizonText = computed(() => mapped('plan.horizons', result.value?.horizon_note ?? null));
const confText = computed(() => (result.value?.confidence && te(`plan.confidence.${result.value.confidence}`) ? t(`plan.confidence.${result.value.confidence}`) : null));

// ---- events ----
const events = ref<PlanEvent[]>([]);
const eventsLoading = ref(true);
const sortedEvents = computed(() => {
  const up = events.value.filter((e) => !e.is_past).sort((a, b) => a.start_date.localeCompare(b.start_date));
  const past = events.value.filter((e) => e.is_past).sort((a, b) => b.start_date.localeCompare(a.start_date));
  return [...up, ...past];
});
async function loadEvents() {
  try { events.value = (await eventsApi.list()).data; } catch { /* the page still works without the list */ }
  eventsLoading.value = false;
}
const evPct = (e: PlanEvent) => (e.status === 'ok' && e.probability_any !== null
  ? (e.probability_any < 0.01 ? '<1%' : e.probability_any > 0.99 ? '>99%' : `${Math.round(e.probability_any * 100)}%`) : null);
const evSub = (e: PlanEvent) => {
  if (e.is_past) return t('plan.events.past');
  if (e.status === 'ok') return null;
  return t(`plan.status.${e.status}`);
};

// ---- sheet: save / edit ----
const sheet = ref<{ id: number | null; name: string; start: string; end: string } | null>(null);
const sheetBusy = ref(false);
const sheetError = ref<string | null>(null);
const confirmDelete = ref(false);
function openSave() { sheetError.value = null; confirmDelete.value = false; sheet.value = { id: null, name: '', start: start.value, end: end.value }; }
function openEdit(e: PlanEvent) { sheetError.value = null; confirmDelete.value = false; sheet.value = { id: e.id, name: e.name, start: e.start_date, end: e.end_date }; }
function sheetValid(): string | null {
  const s = sheet.value!;
  if (!s.name.trim()) return t('plan.errors.name');
  if (!s.start || !s.end) return t('plan.errors.pick');
  if (s.end < s.start) return t('plan.errors.order');
  if (differenceInCalendarDays(parseISO(s.end), parseISO(s.start)) + 1 > 60) return t('plan.errors.tooLong');
  return null;
}
async function submitSheet() {
  const s = sheet.value!;
  sheetError.value = sheetValid();
  if (sheetError.value) return;
  sheetBusy.value = true;
  const body = { name: s.name.trim(), start_date: s.start, end_date: s.end };
  try {
    if (s.id === null) await eventsApi.create(body); else await eventsApi.update(s.id, body);
    toast.success(t(s.id === null ? 'plan.toast.saved' : 'plan.toast.updated'));
    sheet.value = null;
    await loadEvents();
  } catch (e: any) {
    sheetError.value = apiMessage(e, t('plan.errors.generic'));
  } finally { sheetBusy.value = false; }
}
async function removeEvent() {
  const s = sheet.value!;
  if (s.id === null) return;
  if (!confirmDelete.value) { confirmDelete.value = true; return; }
  sheetBusy.value = true;
  try { await eventsApi.remove(s.id); toast.success(t('plan.toast.deleted')); sheet.value = null; await loadEvents(); }
  catch (e: any) { sheetError.value = apiMessage(e, t('plan.errors.generic')); }
  finally { sheetBusy.value = false; }
}
function checkEvent(e: PlanEvent) {
  start.value = e.start_date; end.value = e.end_date;
  (document.querySelector('main') as HTMLElement | null)?.scrollTo({ top: 0, behavior: 'smooth' });
}

onMounted(() => { check(); loadEvents(); if (!reports.forecast) reports.fetchForecast(); });
</script>

<template>
  <div class="mx-auto max-w-lg px-5 pt-7 pb-10">
    <p class="eyebrow">{{ $t('plan.eyebrow') }}</p>
    <h1 class="page-title mt-1.5 text-balance">{{ $t('plan.title') }}</h1>
    <p class="mt-2 text-[0.9375rem] leading-snug text-ink-soft">{{ $t('plan.intro') }}</p>

    <!-- inputs -->
    <section class="mt-5 grid grid-cols-2 gap-3" :aria-label="$t('plan.pick')">
      <div class="min-w-0">
        <label for="plan-start" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('plan.from') }}</label>
        <DateField id="plan-start" v-model="start" :label="$t('plan.from')" @change="onStart" />
      </div>
      <div class="min-w-0">
        <label for="plan-end" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('plan.to') }}</label>
        <DateField id="plan-end" v-model="end" :min="start" :max="maxEnd" :label="$t('plan.to')" />
      </div>
    </section>
    <p v-if="formError" class="mt-2 text-sm text-danger" role="alert">{{ formError }}</p>
    <p v-else-if="apiError" class="mt-2 text-sm text-danger" role="alert">{{ apiError }}</p>

    <!-- answer -->
    <section class="answer card mt-5 p-5" aria-live="polite" :aria-busy="checking">
      <Skeleton v-if="!result && !formError && !apiError" variant="card" class="!border-0" />
      <template v-else-if="result">
        <template v-if="ok">
          <p class="eyebrow">{{ rangeText }}</p>
          <p class="mt-2 flex items-baseline gap-2">
            <span class="display-number" :class="{ 'opacity-60': checking }" style="color: var(--color-period-ink)">{{ pct }}<span class="text-[2rem]">%</span></span>
          </p>
          <p class="mt-1 font-display text-[1.25rem] leading-snug text-balance">{{ answerSentence }}</p>

          <p class="mt-3 text-[0.875rem] leading-snug text-ink-soft">{{ startNote }} {{ $t('plan.countsAny') }}<template v-if="higherThanStart"> {{ $t('plan.higherThan', { pct: startConf }) }}</template></p>
          <div v-if="cells.length" class="mt-5">
            <p class="mb-2 text-[0.8125rem] font-semibold text-ink-soft">{{ $t('plan.timelineTitle') }}</p>
            <div class="tl" :style="{ gridTemplateColumns: `repeat(${cells.length}, minmax(0, 1fr))` }" role="img" :aria-label="$t('plan.timelineLabel')">
              <span v-for="c in cells" :key="c.date" class="tl-col" :title="c.label">
                <i class="tl-bar" :class="{ likely: c.likely }" :style="{ height: c.h + '%' }"></i>
              </span>
            </div>
            <div v-if="winSpan" class="tl-win" :style="{ gridTemplateColumns: `repeat(${cells.length}, minmax(0, 1fr))` }" aria-hidden="true">
              <span class="tl-win-line" :style="{ gridColumn: `${winSpan.from} / ${winSpan.to}` }"><em>{{ $t('plan.likelyStartLabel') }}</em></span>
            </div>
            <div v-if="cells.length <= 14" class="tl-pcts" :style="{ gridTemplateColumns: `repeat(${cells.length}, minmax(0, 1fr))` }" aria-hidden="true">
              <span v-for="c in cells" :key="c.date">{{ c.pct }}</span>
            </div>
            <div class="tl-ticks" :style="{ gridTemplateColumns: `repeat(${cells.length}, minmax(0, 1fr))` }" aria-hidden="true">
              <span v-for="(c, i) in cells" :key="c.date">{{ i % tickEvery === 0 || i === cells.length - 1 && cells.length <= 14 ? c.day : '' }}</span>
            </div>
            <p class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-soft">
              <span class="inline-flex items-center gap-1.5"><i class="sw likely"></i>{{ $t('plan.legendLikely') }}</span>
              <span class="inline-flex items-center gap-1.5"><i class="sw"></i>{{ $t('plan.legendPossible') }}</span>
              <span v-if="winSpan" class="inline-flex items-center gap-1.5"><i class="sw-line"></i>{{ $t('plan.likelyStartLabel') }}</span>
            </p>
            <p v-if="winSpan" class="mt-1.5 text-xs text-ink-soft">{{ $t('plan.peakNote') }}</p>
          </div>

          <dl class="mt-5 space-y-1.5 border-t border-line pt-4 text-[0.875rem] leading-snug text-ink-soft">
            <p v-if="confText">{{ confText }}</p>
            <p v-if="horizonText">{{ horizonText }}</p>
            <p v-if="reasonText">{{ reasonText }}</p>
            <p v-if="result.includes_past_dates">{{ $t('plan.includesPast') }}</p>
          </dl>
          <button type="button" class="btn btn-primary mt-5 w-full gap-2" @click="openSave"><BookmarkIcon class="h-5 w-5" />{{ $t('plan.save') }}</button>
        </template>

        <template v-else>
          <p class="eyebrow">{{ rangeText }}</p>
          <p class="mt-2 font-display text-[1.375rem] leading-snug text-balance">{{ $t(`plan.status.${result.status}Title`) }}</p>
          <p class="mt-2 text-[0.9375rem] leading-snug text-ink-soft">{{ mapped('plan.reasons', result.reason) || $t(`plan.status.${result.status}`) }}</p>
          <p v-if="horizonText" class="mt-2 text-[0.875rem] leading-snug text-ink-soft">{{ horizonText }}</p>
        </template>
      </template>
    </section>

    <!-- saved events -->
    <section class="mt-9" aria-labelledby="saved-h">
      <h2 id="saved-h" class="section-title">{{ $t('plan.events.title') }}</h2>
      <Skeleton v-if="eventsLoading" variant="rows" :rows="2" class="mt-3" />
      <p v-else-if="!sortedEvents.length" class="mt-2 text-[0.9375rem] leading-snug text-ink-soft">{{ $t('plan.events.empty') }}</p>
      <ul v-else class="mt-3 flex flex-col gap-3">
        <li v-for="e in sortedEvents" :key="e.id" class="ev card flex items-center gap-3 !rounded-3xl py-3 pl-4 pr-2" :class="{ past: e.is_past }">
          <button type="button" class="min-w-0 flex-1 text-left" @click="checkEvent(e)">
            <span class="block truncate font-semibold">{{ e.name }}</span>
            <span class="block text-[0.8125rem] text-ink-soft">{{ formatRange(e.start_date, e.end_date, locale) }}<template v-if="evSub(e)"> · {{ evSub(e) }}</template></span>
          </button>
          <span v-if="evPct(e)" class="ev-pct phase-chip phase-period !text-[0.9375rem]">{{ evPct(e) }}</span>
          <button type="button" class="grid h-11 w-11 flex-none place-items-center rounded-full text-ink-soft" :aria-label="$t('plan.events.edit', { name: e.name })" @click="openEdit(e)"><PencilSquareIcon class="h-5 w-5" /></button>
        </li>
      </ul>
    </section>

    <BottomSheet v-if="sheet" :title="sheet.id === null ? $t('plan.sheet.saveTitle') : $t('plan.sheet.editTitle')" :close-label="$t('calendar.close')" @close="sheet = null">
      <form class="flex flex-col gap-4" @submit.prevent="submitSheet" novalidate>
        <div>
          <label for="ev-name" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('plan.sheet.name') }}</label>
          <input id="ev-name" v-model="sheet.name" maxlength="120" class="block w-full" :placeholder="$t('plan.sheet.namePlaceholder')" autocomplete="off" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div class="min-w-0"><label for="ev-s" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('plan.from') }}</label><DateField id="ev-s" v-model="sheet.start" :label="$t('plan.from')" /></div>
          <div class="min-w-0"><label for="ev-e" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('plan.to') }}</label><DateField id="ev-e" v-model="sheet.end" :min="sheet.start" :label="$t('plan.to')" /></div>
        </div>
        <p v-if="sheetError" class="rounded-2xl bg-danger-soft px-3.5 py-2.5 text-[0.8125rem] leading-snug text-danger-ink" role="alert">{{ sheetError }}</p>
        <button type="submit" class="btn btn-primary w-full" :disabled="sheetBusy">{{ $t('common.save') }}</button>
        <button v-if="sheet.id !== null" type="button" class="btn w-full" :class="confirmDelete ? 'btn-danger' : 'btn-secondary'" :disabled="sheetBusy" @click="removeEvent">
          {{ confirmDelete ? $t('plan.sheet.deleteSure') : $t('plan.sheet.delete') }}
        </button>
      </form>
    </BottomSheet>
  </div>
</template>

<style scoped>
.tl { display: grid; gap: 3px; height: 5.5rem; align-items: end; }
.tl-col { display: flex; align-items: flex-end; height: 100%; min-width: 0; }
.tl-bar { display: block; width: 100%; border-radius: .4rem .4rem .2rem .2rem;
  background: color-mix(in srgb, var(--color-period) 26%, var(--color-surface));
  border: 1.5px dashed color-mix(in srgb, var(--color-period) 60%, transparent); }
.tl-bar.likely { background: var(--color-period); border: 1.5px solid var(--color-period); }
.tl-pcts { display: grid; gap: 3px; margin-top: .25rem; font-size: .6875rem; font-weight: 600; color: var(--color-ink); text-align: center; font-variant-numeric: tabular-nums; }
.tl-win { display: grid; gap: 3px; margin-top: .375rem; }
.tl-win-line { display: flex; justify-content: center; border-top: 3px solid var(--color-ink); border-radius: 9999px; padding-top: .125rem; min-width: 0; }
.tl-win-line em { font-style: normal; font-size: .6875rem; font-weight: 600; color: var(--color-ink); white-space: nowrap; }
.sw-line { display: inline-block; width: 1rem; height: 0; border-top: 3px solid var(--color-ink); border-radius: 9999px; }
.tl-ticks { display: grid; gap: 3px; margin-top: .375rem; font-size: .6875rem; color: var(--color-ink-soft); text-align: center; font-variant-numeric: tabular-nums; }
.sw { display: inline-block; width: 1rem; height: .75rem; border-radius: .25rem; background: color-mix(in srgb, var(--color-period) 26%, var(--color-surface)); border: 1.5px dashed color-mix(in srgb, var(--color-period) 60%, transparent); }
.sw.likely { background: var(--color-period); border-color: var(--color-period); }
.ev.past { opacity: .6; }
.ev-pct { flex: none; }
</style>
