<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { LockClosedIcon, ChevronDownIcon } from '@heroicons/vue/24/outline';
import { haApi, webhookApi, apiMessage, WEBHOOK_EVENTS, type HomeAssistant, type Webhook } from '@/api/plan';
import ConfirmationModal from '@/components/ConfirmationModal.vue';
import ShownSecret from '@/components/ShownSecret.vue';
import Skeleton from '@/components/Skeleton.vue';
import { useToast } from '@/composables/useToast';

const { t } = useI18n();
const toast = useToast();
const open = ref(false);
const loaded = ref(false);
const busy = ref(false);
const error = ref<string | null>(null);

// Home Assistant
const ha = ref<HomeAssistant>({ enabled: false, include_fertile: false });
const haFertile = ref(false);
const haUrl = ref<string | null>(null);
const haRotateAsk = ref(false);
const haOffAsk = ref(false);

// Webhooks
const hooks = ref<Webhook[]>([]);
const newHook = reactive({ url: '', events: ['period_started', 'period_ended', 'period_expected_soon'] as string[] });
const hookError = ref<string | null>(null);
const secret = ref<{ id: number; value: string } | null>(null);
const results = reactive<Record<number, { ok: boolean; text: string }>>({});
const deleteId = ref<number | null>(null);
const deleteAsk = ref(false);
const rotateId = ref<number | null>(null);
const rotateAsk = ref(false);

async function load() {
  if (loaded.value) return;
  try {
    const [h, w] = await Promise.all([haApi.get(), webhookApi.list()]);
    ha.value = h.data; haFertile.value = h.data.include_fertile; hooks.value = w.data;
  } catch (e: any) { error.value = apiMessage(e, t('auto.errors.generic')); }
  loaded.value = true;
}
onMounted(() => { /* collapsed by default: load lazily on first open */ });
function onToggle(e: Event) { open.value = (e.target as HTMLDetailsElement).open; if (open.value) load(); }

const fullUrl = (r: { path: string; url: string | null }) => r.url ?? `${location.origin}${r.path}`;
async function haCreate() {
  busy.value = true; error.value = null;
  try { const r = await haApi.create(haFertile.value); haUrl.value = fullUrl(r.data); ha.value = { enabled: true, include_fertile: haFertile.value }; }
  catch (e: any) { error.value = apiMessage(e, t('auto.errors.generic')); }
  finally { busy.value = false; }
}
async function haSave() {
  busy.value = true; error.value = null;
  try { const r = await haApi.update(haFertile.value); ha.value = r.data; toast.success(t('auto.saved')); }
  catch (e: any) { error.value = apiMessage(e, t('auto.errors.generic')); }
  finally { busy.value = false; }
}
async function haOff() {
  busy.value = true; error.value = null;
  try { await haApi.revoke(); ha.value = { ...ha.value, enabled: false }; haUrl.value = null; toast.success(t('auto.ha.off')); }
  catch (e: any) { error.value = apiMessage(e, t('auto.errors.generic')); }
  finally { busy.value = false; }
}

async function addHook() {
  busy.value = true; hookError.value = null;
  try {
    const r = await webhookApi.create({ url: newHook.url.trim(), events: newHook.events });
    hooks.value.push({ ...r.data, secret: undefined });
    secret.value = { id: r.data.id, value: r.data.secret || '' };
    newHook.url = '';
  } catch (e: any) {
    const m = apiMessage(e, t('auto.errors.generic'));
    hookError.value = /ALLOW_PRIVATE_WEBHOOKS/.test(m) && !m.includes('=1') ? `${m} ${t('auto.hooks.privateHint')}` : m;
  } finally { busy.value = false; }
}
async function test(h: Webhook) {
  busy.value = true;
  try {
    const r = (await webhookApi.test(h.id)).data;
    results[h.id] = r.delivered ? { ok: true, text: t('auto.hooks.testOk', { status: r.status }) } : { ok: false, text: r.error || t('auto.hooks.testFail', { status: r.status }) };
  } catch (e: any) { results[h.id] = { ok: false, text: apiMessage(e, t('auto.errors.generic')) }; }
  finally { busy.value = false; }
}
async function toggleActive(h: Webhook) {
  try { const r = await webhookApi.update(h.id, { active: !h.active }); Object.assign(h, r.data); }
  catch (e: any) { hookError.value = apiMessage(e, t('auto.errors.generic')); }
}
async function removeHook() {
  if (deleteId.value == null) return;
  const id = deleteId.value;
  try { await webhookApi.remove(id); hooks.value = hooks.value.filter((h) => h.id !== id); if (secret.value?.id === id) secret.value = null; }
  catch (e: any) { hookError.value = apiMessage(e, t('auto.errors.generic')); }
}
async function rotateSecret() {
  if (rotateId.value == null) return;
  try { const r = await webhookApi.rotate(rotateId.value); secret.value = { id: r.data.id, value: r.data.secret || '' }; }
  catch (e: any) { hookError.value = apiMessage(e, t('auto.errors.generic')); }
}
const ask = (kind: 'delete' | 'rotate', id: number) => { if (kind === 'delete') { deleteId.value = id; deleteAsk.value = true; } else { rotateId.value = id; rotateAsk.value = true; } };
</script>

<template>
  <section aria-labelledby="auto-heading" class="card p-6">
    <details @toggle="onToggle">
      <summary class="flex cursor-pointer list-none items-start justify-between gap-3">
        <span>
          <h3 id="auto-heading" class="section-title mb-1">{{ $t('auto.title') }}</h3>
          <span class="block text-[0.9375rem] leading-snug text-ink-soft">{{ $t('auto.intro') }}</span>
        </span>
        <ChevronDownIcon class="mt-1 h-5 w-5 flex-none text-ink-soft transition-transform" :class="{ 'rotate-180': open }" />
      </summary>

      <div class="mt-5">
        <p class="mb-4 rounded-2xl bg-surface-muted px-3.5 py-2.5 text-[0.8125rem] leading-snug"><LockClosedIcon class="mr-1.5 inline h-4 w-4 align-[-3px]" />{{ $t('auto.private') }}</p>
        <Skeleton v-if="!loaded" variant="line" />
        <template v-else>
          <p v-if="error" class="mb-4 rounded-2xl bg-danger-soft px-3.5 py-2.5 text-[0.8125rem] leading-snug text-danger-ink" role="alert">{{ error }}</p>

          <!-- Home Assistant -->
          <h4 class="mb-1 text-base font-semibold">{{ $t('auto.ha.title') }}</h4>
          <p class="mb-3 text-[0.875rem] leading-snug text-ink-soft">{{ $t('auto.ha.intro') }} {{ $t('auto.ha.guide') }}</p>
          <ShownSecret v-if="haUrl" id="ha-url" :value="haUrl" :title="$t('auto.ha.urlTitle')" :note="$t('auto.ha.urlOnce')" />
          <label class="mb-3 flex items-start gap-3">
            <input type="checkbox" v-model="haFertile" class="auto-check" />
            <span><span class="block text-[0.9375rem] font-medium">{{ $t('auto.ha.fertile') }}</span><span class="block text-xs leading-snug text-ink-soft">{{ $t('auto.ha.fertileHelp') }}</span></span>
          </label>
          <button v-if="!ha.enabled" type="button" class="btn btn-primary w-full" :disabled="busy" @click="haCreate">{{ $t('auto.ha.create') }}</button>
          <template v-else>
            <button type="button" class="btn btn-primary w-full" :disabled="busy || haFertile === ha.include_fertile" @click="haSave">{{ $t('common.save') }}</button>
            <p v-if="!haUrl" class="mt-2 text-xs leading-snug text-ink-soft">{{ $t('auto.ha.active') }}</p>
            <div class="mt-3 flex flex-col gap-2 border-t border-line pt-4 sm:flex-row">
              <button type="button" class="btn btn-secondary flex-1" :disabled="busy" @click="haRotateAsk = true">{{ $t('auto.ha.rotate') }}</button>
              <button type="button" class="btn btn-secondary flex-1" :disabled="busy" @click="haOffAsk = true">{{ $t('auto.ha.turnOff') }}</button>
            </div>
          </template>

          <!-- Webhooks -->
          <h4 class="mb-1 mt-7 border-t border-line pt-5 text-base font-semibold">{{ $t('auto.hooks.title') }}</h4>
          <p class="mb-3 text-[0.875rem] leading-snug text-ink-soft">{{ $t('auto.hooks.intro') }}</p>

          <ShownSecret v-if="secret" id="hook-secret" :value="secret.value" :title="$t('auto.hooks.secretTitle')" :note="$t('auto.hooks.secretOnce')" />

          <ul v-if="hooks.length" class="mb-4 space-y-3">
            <li v-for="h in hooks" :key="h.id" class="rounded-2xl border border-line p-3.5">
              <p class="break-all text-[0.875rem] font-semibold">{{ h.url }}</p>
              <p class="mt-1 text-xs leading-snug text-ink-soft">{{ h.events.map((e) => $t(`auto.events.${e}`)).join(' · ') }}</p>
              <p v-if="!h.active" class="mt-1 text-xs font-medium text-danger-ink">{{ $t('auto.hooks.paused') }}</p>
              <p v-if="results[h.id]" class="mt-2 rounded-xl px-3 py-2 text-xs leading-snug" :class="results[h.id].ok ? 'bg-success-soft text-success-ink' : 'bg-danger-soft text-danger-ink'" role="status">{{ results[h.id].text }}</p>
              <div class="mt-3 flex flex-wrap gap-2">
                <button type="button" class="btn btn-secondary !min-h-10 !px-3.5 !text-sm" :disabled="busy" @click="test(h)">{{ $t('auto.hooks.test') }}</button>
                <button type="button" class="btn btn-secondary !min-h-10 !px-3.5 !text-sm" @click="toggleActive(h)">{{ h.active ? $t('auto.hooks.pause') : $t('auto.hooks.resume') }}</button>
                <button type="button" class="btn btn-secondary !min-h-10 !px-3.5 !text-sm" @click="ask('rotate', h.id)">{{ $t('auto.hooks.rotate') }}</button>
                <button type="button" class="btn btn-secondary !min-h-10 !px-3.5 !text-sm" @click="ask('delete', h.id)">{{ $t('auto.hooks.delete') }}</button>
              </div>
            </li>
          </ul>

          <form class="flex flex-col gap-3" @submit.prevent="addHook">
            <div>
              <label for="hook-url" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('auto.hooks.url') }}</label>
              <input id="hook-url" v-model="newHook.url" type="url" required minlength="8" maxlength="500" class="block w-full" placeholder="https://example.com/hook" />
            </div>
            <fieldset class="space-y-2">
              <legend class="mb-1 text-sm font-medium text-ink-soft">{{ $t('auto.hooks.events') }}</legend>
              <label v-for="ev in WEBHOOK_EVENTS" :key="ev" class="flex items-start gap-3">
                <input type="checkbox" :value="ev" v-model="newHook.events" class="auto-check" />
                <span class="text-[0.9375rem]">{{ $t(`auto.events.${ev}`) }}<span v-if="ev === 'fertile_window_starting'" class="ml-1.5 text-xs text-ink-soft">{{ $t('auto.hooks.optIn') }}</span></span>
              </label>
            </fieldset>
            <p v-if="hookError" class="rounded-2xl bg-danger-soft px-3.5 py-2.5 text-[0.8125rem] leading-snug text-danger-ink" role="alert">{{ hookError }}</p>
            <button type="submit" class="btn btn-primary w-full" :disabled="busy || !newHook.events.length || hooks.length >= 5">{{ $t('auto.hooks.add') }}</button>
          </form>
        </template>
      </div>
    </details>

    <ConfirmationModal v-model="haRotateAsk" :title="$t('auto.ha.rotateTitle')" :message="$t('auto.ha.rotateMessage')" :confirm-text="$t('auto.ha.rotate')" :cancel-text="$t('common.cancel')" @confirm="haCreate" />
    <ConfirmationModal v-model="haOffAsk" :title="$t('auto.ha.offTitle')" :message="$t('auto.ha.offMessage')" :confirm-text="$t('auto.ha.turnOff')" :cancel-text="$t('common.cancel')" confirm-button-type="danger" @confirm="haOff" />
    <ConfirmationModal v-model="deleteAsk" :title="$t('auto.hooks.deleteTitle')" :message="$t('auto.hooks.deleteMessage')" :confirm-text="$t('auto.hooks.delete')" :cancel-text="$t('common.cancel')" confirm-button-type="danger" @confirm="removeHook" />
    <ConfirmationModal v-model="rotateAsk" :title="$t('auto.hooks.rotateTitle')" :message="$t('auto.hooks.rotateMessage')" :confirm-text="$t('auto.hooks.rotate')" :cancel-text="$t('common.cancel')" @confirm="rotateSecret" />
  </section>
</template>

<style scoped>
summary::-webkit-details-marker { display: none; }
.auto-check { flex: none; width: 1.375rem; height: 1.375rem; padding: 0; margin-top: .125rem; accent-color: var(--color-primary); }
</style>
