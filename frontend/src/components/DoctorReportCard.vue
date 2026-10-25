<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { DocumentTextIcon } from '@heroicons/vue/24/outline';
import { doctorApi, apiMessage } from '@/api/plan';

const { t } = useI18n();
const months = ref(12);
const busy = ref(false);
const error = ref<string | null>(null);

async function open() {
  busy.value = true; error.value = null;
  // open synchronously so popup blockers allow it, then point it at the blob
  const w = window.open('', '_blank');
  try {
    const r = await doctorApi.html(months.value);
    const url = URL.createObjectURL(new Blob([r.data], { type: 'text/html;charset=utf-8' }));
    if (w) w.location.href = url; else location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 5 * 60_000);
  } catch (e: any) { w?.close(); error.value = apiMessage(e, t('doctor.error')); }
  finally { busy.value = false; }
}
</script>

<template>
  <section aria-labelledby="doctor-heading" class="card p-6">
    <h3 id="doctor-heading" class="section-title mb-1">{{ $t('doctor.title') }}</h3>
    <p class="mb-4 text-[0.9375rem] leading-snug text-ink-soft">{{ $t('doctor.intro') }}</p>
    <div class="flex flex-col gap-4">
      <div>
        <label for="doctor-months" class="mb-1.5 block text-sm font-medium text-ink-soft">{{ $t('doctor.range') }}</label>
        <select id="doctor-months" v-model.number="months" class="block w-full">
          <option v-for="m in [6, 12, 24]" :key="m" :value="m">{{ $t('doctor.months', { n: m }) }}</option>
        </select>
      </div>
      <p v-if="error" class="rounded-2xl bg-danger-soft px-3.5 py-2.5 text-[0.8125rem] leading-snug text-danger-ink" role="alert">{{ error }}</p>
      <button type="button" class="btn btn-primary w-full gap-1.5" :disabled="busy" @click="open"><DocumentTextIcon class="h-5 w-5" />{{ $t('doctor.open') }}</button>
      <p class="text-xs leading-snug text-ink-soft">{{ $t('doctor.note') }}</p>
    </div>
  </section>
</template>
