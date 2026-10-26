<script setup lang="ts">
const repoUrl = 'https://github.com/fromej-dev/cycle-tracker'
</script>

<template>
  <footer class="border-t border-line">
    <div class="mx-auto max-w-6xl px-4 sm:px-6 py-10 flex flex-col sm:flex-row gap-6 sm:items-center sm:justify-between">
      <div>
        <div class="flex gap-2.5 items-center font-display text-lg text-primary">
          <img src="/assets/icons/180_tp.png" alt="" class="h-7 w-7 rounded-[25%]">
          {{ $t('common.title') }}
        </div>
        <p class="text-ink-soft text-sm mt-2">{{ $t('homepage.footer.tagline') }}</p>
      </div>
      <div class="text-sm text-ink-soft sm:text-right space-y-1.5">
        <p>
          <a :href="repoUrl" class="text-primary hover:text-primary-hover transition-colors">{{ $t('homepage.footer.source') }}</a>
          · {{ $t('homepage.footer.license') }}
        </p>
        <p>
          © {{ new Date().getFullYear() }} {{ $t('homepage.footer.madeBy') }}
          <a href="https://fromej.nl" class="text-primary hover:text-primary-hover transition-colors">FromEJ</a>
        </p>
      </div>
    </div>
  </footer>
</template>
