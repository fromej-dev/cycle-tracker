<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { LockClosedIcon } from '@heroicons/vue/24/outline';
import { partnerApi, apiMessage } from '@/api/plan';
import ConfirmationModal from '@/components/ConfirmationModal.vue';
import ShownSecret from '@/components/ShownSecret.vue';
import Skeleton from '@/components/Skeleton.vue';
import { useToast } from '@/composables/useToast';

const { t } = useI18n();
const toast = useToast();
const loading = ref(true);
const busy = ref(false);
const error = ref<string | null>(null);
const enabled = ref(false);
const shownUrl = ref<string | null>(null);
const rotateAsk = ref(false);
const offAsk = ref(false);
const dirty = ref(false);
const form = reactive({ name: '', window_days: 3, fertile: false });

onMounted(async () => {
  try { const r = await partnerApi.get(); enabled.value = r.data.enabled; if (r.data.enabled) fill(r.data); }
  catch (e: any) { error.value = apiMessage(e, t('partner.errors.generic')); }
  loading.value = false;
});
function fill(p: { name: string; scope: { fertile: boolean; window_days: number } }) {
  form.name = p.name; form.window_days = p.scope.window_days; form.fertile = p.scope.fertile;
}
const body = () => ({ name: form.name.trim(), scope: { fertile: form.fertile, window_days: Number(form.window_days) } });
const fullUrl = (r: { path: string; url: string | null }) => r.url ?? `${location.origin}${r.path}`;
const valid = computed(() => form.window_days >= 2 && form.window_days <= 14);

async function create() {
  busy.value = true; error.value = null;
  try { const r = await partnerApi.create(body()); shownUrl.value = fullUrl(r.data); enabled.value = true; dirty.value = false; }
  catch (e: any) { error.value = apiMessage(e, t('partner.errors.generic')); }
  finally { busy.value = false; }
}
async function save() {
  busy.value = true; error.value = null;
  try { const r = await partnerApi.update(body()); fill(r.data); dirty.value = false; toast.success(t('partner.saved')); }
  catch (e: any) { error.value = apiMessage(e, t('partner.errors.generic')); }
  finally { busy.value = false; }
}
async function turnOff() {
  busy.value = true; error.value = null;
  try { await partnerApi.revoke(); enabled.value = false; shownUrl.value = null; toast.success(t('partner.off')); }
  catch (e: any) { error.value = apiMessage(e, t('partner.errors.generic')); }
  finally { busy.value = false; }
}
</script>

<template>
  <section aria-labelledby="partner-heading" class="card p-6">
    <h3 id="partner-heading" class="section-title mb-1">{{ $t('partner.title') }}</h3>
    <p class="mb-4 text-[0.9375rem] leading-snug text-ink-soft">{{ $t('partner.intro') }}</p>
    <p class="mb-4 rounded-2xl bg-surface-muted px-3.5 py-2.5 text-[0.8125rem] leading-snug"><LockClosedIcon class="mr-1.5 inline h-4 w-4 align-[-3px]" />{{ $t('partner.private') }}</p>
    <Skeleton v-if="loading" variant="line" />
    <template v-else>
      <ShownSecret v-if="shownUrl" id="partner-url" :value="shownUrl" :title="$t('partner.urlTitle')" :note="$t('partner.urlOnce')" />
      <form class="flex flex-col gap-4" @submit.prevent="enabled ? save() : create()" @input="dirty = true">
        <div>
          <label for="partner-name" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('partner.name') }}</label>
          <input id="partner-name" v-model="form.name" maxlength="40" class="block w-full" :placeholder="$t('partner.namePlaceholder')" />
          <p class="mt-1.5 text-xs leading-snug text-ink-soft">{{ $t('partner.nameHelp') }}</p>
        </div>
        <div>
          <label for="partner-days" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('partner.window') }}</label>
          <input id="partner-days" v-model.number="form.window_days" type="number" min="2" max="14" inputmode="numeric" class="block w-full" />
          <p class="mt-1.5 text-xs leading-snug text-ink-soft">{{ $t('partner.windowHelp') }}</p>
        </div>
        <label class="flex items-start gap-3">
          <input type="checkbox" v-model="form.fertile" class="share-check" />
          <span><span class="block text-[0.9375rem] font-medium">{{ $t('partner.fertile') }}</span><span class="block text-xs leading-snug text-ink-soft">{{ $t('partner.fertileHelp') }}</span></span>
        </label>
        <p v-if="error" class="rounded-2xl bg-danger-soft px-3.5 py-2.5 text-[0.8125rem] leading-snug text-danger-ink" role="alert">{{ error }}</p>
        <button v-if="!enabled" type="submit" class="btn btn-primary w-full" :disabled="busy || !valid">{{ $t('partner.create') }}</button>
        <template v-else>
          <button type="submit" class="btn btn-primary w-full" :disabled="busy || !dirty || !valid">{{ $t('common.save') }}</button>
          <p v-if="!shownUrl" class="text-xs leading-snug text-ink-soft">{{ $t('partner.active') }}</p>
          <div class="flex flex-col gap-2 border-t border-line pt-4 sm:flex-row">
            <button type="button" class="btn btn-secondary flex-1" :disabled="busy" @click="rotateAsk = true">{{ $t('partner.rotate') }}</button>
            <button type="button" class="btn btn-secondary flex-1" :disabled="busy" @click="offAsk = true">{{ $t('partner.turnOff') }}</button>
          </div>
        </template>
      </form>
    </template>
    <ConfirmationModal v-model="rotateAsk" :title="$t('partner.rotateTitle')" :message="$t('partner.rotateMessage')" :confirm-text="$t('partner.rotateConfirm')" :cancel-text="$t('common.cancel')" @confirm="create" />
    <ConfirmationModal v-model="offAsk" :title="$t('partner.offTitle')" :message="$t('partner.offMessage')" :confirm-text="$t('partner.turnOff')" :cancel-text="$t('common.cancel')" confirm-button-type="danger" @confirm="turnOff" />
  </section>
</template>

<style scoped>
.share-check { flex: none; width: 1.375rem; height: 1.375rem; padding: 0; margin-top: .125rem; accent-color: var(--color-primary); }
</style>
