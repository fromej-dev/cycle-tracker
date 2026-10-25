<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ClipboardDocumentIcon, CheckIcon, LockClosedIcon } from '@heroicons/vue/24/outline';
import { feedApi, apiMessage, type CalendarFeed } from '@/api/plan';
import ConfirmationModal from '@/components/ConfirmationModal.vue';
import Skeleton from '@/components/Skeleton.vue';
import { useToast } from '@/composables/useToast';

const { t } = useI18n();
const toast = useToast();
const loading = ref(true);
const busy = ref(false);
const error = ref<string | null>(null);
const feed = ref<CalendarFeed | null>(null);
const shownUrl = ref<string | null>(null); // the secret link is shown ONCE, right after creating / rotating
const copied = ref(false);
const rotateAsk = ref(false);
const offAsk = ref(false);
const browserTz = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch { return ''; } })();

const FALLBACK_ZONES = ['UTC', 'Europe/Amsterdam', 'Europe/London', 'Europe/Berlin', 'Europe/Paris', 'Europe/Madrid', 'Europe/Rome', 'Europe/Lisbon', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Sao_Paulo', 'Asia/Dubai', 'Asia/Kolkata', 'Asia/Singapore', 'Asia/Tokyo', 'Australia/Sydney', 'Pacific/Auckland'];
const baseZones = (() => { try { const z = (Intl as any).supportedValuesOf?.('timeZone') as string[] | undefined; if (z?.length) return z.includes('UTC') ? z : ['UTC', ...z]; } catch { /* old browser */ } return FALLBACK_ZONES; })();
const form = reactive({ label: '🌙', include_fertile: false, fertile_label: '', mark_estimates: false, timezone: browserTz });
function fill(f: CalendarFeed) {
  form.label = f.label || '🌙';
  form.include_fertile = f.include_fertile;
  form.fertile_label = f.fertile_label ?? '';
  form.mark_estimates = f.mark_estimates;
  form.timezone = f.timezone || browserTz;
}
const dirty = ref(false);
const zones = computed(() => (form.timezone && !baseZones.includes(form.timezone) ? [form.timezone, ...baseZones] : baseZones));

onMounted(async () => {
  try { const r = await feedApi.get(); feed.value = r.data; fill(r.data); }
  catch (e: any) { error.value = apiMessage(e, t('feed.errors.generic')); }
  loading.value = false;
});

const fullUrl = (r: { path: string; url: string | null }) => r.url ?? `${location.origin}${r.path}`;

async function create() {
  busy.value = true; error.value = null;
  try {
    const r = await feedApi.create(form.timezone || undefined);
    shownUrl.value = fullUrl(r.data);
    // apply the chosen options straight away so the first sync already looks right
    const up = await feedApi.update(payload());
    feed.value = up.data; fill(up.data);
  } catch (e: any) { error.value = apiMessage(e, t('feed.errors.generic')); }
  finally { busy.value = false; }
}
function payload() {
  return { label: form.label.trim() || '🌙', include_fertile: form.include_fertile, fertile_label: form.include_fertile ? (form.fertile_label.trim() || null) : null, mark_estimates: form.mark_estimates, timezone: form.timezone || null };
}
async function save() {
  busy.value = true; error.value = null;
  try { const r = await feedApi.update(payload()); feed.value = r.data; fill(r.data); dirty.value = false; toast.success(t('feed.saved')); }
  catch (e: any) { error.value = apiMessage(e, t('feed.errors.generic')); }
  finally { busy.value = false; }
}
async function rotate() {
  busy.value = true; error.value = null;
  try { const r = await feedApi.create(form.timezone || undefined); shownUrl.value = fullUrl(r.data); copied.value = false; }
  catch (e: any) { error.value = apiMessage(e, t('feed.errors.generic')); }
  finally { busy.value = false; }
}
async function turnOff() {
  busy.value = true; error.value = null;
  try { await feedApi.revoke(); feed.value = { ...(feed.value as CalendarFeed), enabled: false }; shownUrl.value = null; toast.success(t('feed.off')); }
  catch (e: any) { error.value = apiMessage(e, t('feed.errors.generic')); }
  finally { busy.value = false; }
}
async function copy() {
  if (!shownUrl.value) return;
  try { await navigator.clipboard.writeText(shownUrl.value); }
  catch { const el = document.getElementById('feed-url') as HTMLInputElement | null; el?.select(); document.execCommand?.('copy'); }
  copied.value = true; setTimeout(() => (copied.value = false), 2000);
}
const enabled = computed(() => !!feed.value?.enabled);
</script>

<template>
  <section aria-labelledby="feed-heading" class="card p-6">
    <h3 id="feed-heading" class="section-title mb-1">{{ $t('feed.title') }}</h3>
    <p class="mb-4 text-[0.9375rem] leading-snug text-ink-soft">{{ $t('feed.intro') }}</p>
    <p class="mb-4 rounded-2xl bg-surface-muted px-3.5 py-2.5 text-[0.8125rem] leading-snug"><LockClosedIcon class="mr-1.5 inline h-4 w-4 align-[-3px]" />{{ $t('feed.private') }}</p>
    <Skeleton v-if="loading" variant="line" />
    <template v-else>
      <!-- the link, shown once -->
      <div v-if="shownUrl" class="mb-5 rounded-2xl border border-line bg-surface-muted p-4">
        <p class="text-sm font-semibold">{{ $t('feed.urlTitle') }}</p>
        <p class="mt-1 text-[0.8125rem] leading-snug text-ink-soft">{{ $t('feed.urlOnce') }}</p>
        <div class="mt-3 flex items-center gap-2">
          <input id="feed-url" :value="shownUrl" readonly class="min-w-0 flex-1 !text-[0.8125rem]" @focus="($event.target as HTMLInputElement).select()" aria-label="URL" />
          <button type="button" class="btn btn-primary !min-h-11 !px-4 gap-1.5" @click="copy"><component :is="copied ? CheckIcon : ClipboardDocumentIcon" class="h-5 w-5" />{{ copied ? $t('feed.copied') : $t('feed.copy') }}</button>
        </div>
        <div class="mt-4 space-y-2 text-[0.875rem] leading-snug">
          <details v-for="k in ['google', 'apple', 'outlook']" :key="k" class="rounded-xl bg-surface px-3.5 py-2.5">
            <summary class="cursor-pointer font-semibold">{{ $t(`feed.how.${k}.title`) }}</summary>
            <p class="mt-1.5 text-ink-soft">{{ $t(`feed.how.${k}.steps`) }}</p>
          </details>
          <p class="text-xs text-ink-soft">{{ $t('feed.how.delay') }}</p>
        </div>
      </div>

      <form class="flex flex-col gap-4" @submit.prevent="enabled ? save() : create()" @input="dirty = true">
        <div>
          <label for="feed-label" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('feed.label') }}</label>
          <input id="feed-label" v-model="form.label" maxlength="40" class="block w-full" />
          <p class="mt-1.5 text-xs leading-snug text-ink-soft">{{ $t('feed.labelHelp') }}</p>
          <p class="mt-2 flex items-center gap-2 text-xs text-ink-soft">{{ $t('feed.preview') }}
            <span class="preview">{{ (form.label.trim() || '🌙') + (form.mark_estimates ? ' ' + $t('feed.estimateTag') : '') }}</span></p>
        </div>
        <label class="flex items-start gap-3">
          <input type="checkbox" v-model="form.include_fertile" class="feed-check" />
          <span><span class="block text-[0.9375rem] font-medium">{{ $t('feed.fertile') }}</span><span class="block text-xs leading-snug text-ink-soft">{{ $t('feed.fertileHelp') }}</span></span>
        </label>
        <div v-if="form.include_fertile">
          <label for="feed-fl" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('feed.fertileLabel') }}</label>
          <input id="feed-fl" v-model="form.fertile_label" maxlength="40" class="block w-full" :placeholder="$t('feed.fertileLabelPlaceholder')" />
        </div>
        <label class="flex items-start gap-3">
          <input type="checkbox" v-model="form.mark_estimates" class="feed-check" />
          <span><span class="block text-[0.9375rem] font-medium">{{ $t('feed.estimate') }}</span><span class="block text-xs leading-snug text-ink-soft">{{ $t('feed.estimateHelp') }}</span></span>
        </label>
        <div>
          <label for="feed-tz" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('feed.timezone') }}</label>
          <select id="feed-tz" v-model="form.timezone" class="block w-full">
            <option v-for="z in zones" :key="z" :value="z">{{ z }}</option>
          </select>
        </div>
        <p v-if="error" class="rounded-2xl bg-danger-soft px-3.5 py-2.5 text-[0.8125rem] leading-snug text-danger-ink" role="alert">{{ error }}</p>
        <button v-if="!enabled" type="submit" class="btn btn-primary w-full" :disabled="busy">{{ $t('feed.create') }}</button>
        <template v-else>
          <button type="submit" class="btn btn-primary w-full" :disabled="busy || !dirty">{{ $t('common.save') }}</button>
          <p v-if="!shownUrl" class="text-xs leading-snug text-ink-soft">{{ $t('feed.syncing') }}</p>
          <div class="flex flex-col gap-2 border-t border-line pt-4 sm:flex-row">
            <button type="button" class="btn btn-secondary flex-1" :disabled="busy" @click="rotateAsk = true">{{ $t('feed.rotate') }}</button>
            <button type="button" class="btn btn-secondary flex-1" :disabled="busy" @click="offAsk = true">{{ $t('feed.turnOff') }}</button>
          </div>
          <p class="text-xs leading-snug text-ink-soft">{{ $t('feed.rotateHelp') }}</p>
        </template>
      </form>
    </template>

    <ConfirmationModal v-model="rotateAsk" :title="$t('feed.rotateTitle')" :message="$t('feed.rotateMessage')" :confirm-text="$t('feed.rotateConfirm')" :cancel-text="$t('common.cancel')" @confirm="rotate" />
    <ConfirmationModal v-model="offAsk" :title="$t('feed.offTitle')" :message="$t('feed.offMessage')" :confirm-text="$t('feed.turnOff')" :cancel-text="$t('common.cancel')" confirm-button-type="danger" @confirm="turnOff" />
  </section>
</template>

<style scoped>
.feed-check { flex: none; width: 1.375rem; height: 1.375rem; padding: 0; margin-top: .125rem; accent-color: var(--color-primary); }
.preview { display: inline-flex; padding: .125rem .625rem; border-radius: .5rem; background: var(--color-primary-soft); color: var(--color-ink); font-weight: 600; }
</style>
