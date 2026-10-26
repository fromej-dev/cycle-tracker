<template>
  <header class="site-header sticky top-0 z-40 border-b border-line">
    <div class="mx-auto max-w-6xl px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
      <router-link :to="{ name: 'home' }" class="flex gap-2.5 items-center font-display text-lg text-primary shrink-0">
        <img src="/assets/icons/180_tp.png" alt="" class="nav-image dark:hidden">
        <img src="/assets/icons/180_tp_dark.png" alt="" class="nav-image hidden dark:block">
        {{ $t('common.title') }}
      </router-link>

      <nav v-if="sections" class="hidden md:flex items-center gap-1 text-sm font-medium text-ink-soft">
        <a v-for="s in sectionLinks" :key="s.id" :href="`#${s.id}`" @click.prevent="scrollToSection(s.id)"
           class="px-3 py-2 rounded-lg hover:text-ink hover:bg-surface-muted transition-colors">{{ $t(s.label) }}</a>
      </nav>

      <div class="flex items-center gap-1 sm:gap-2">
        <span class="hidden sm:inline-flex"><ThemeToggle /></span>
        <LanguagePicker />
        <router-link :to="{ name: 'login' }"
                     class="hidden sm:inline-flex px-3 py-2 rounded-lg text-sm font-medium text-ink hover:bg-surface-muted">
          {{ $t('common.login') }}
        </router-link>
        <router-link :to="{ name: 'register' }"
                     class="inline-flex items-center whitespace-nowrap px-4 py-2 rounded-full text-sm font-semibold bg-primary text-on-primary hover:bg-primary-hover transition-colors">
          {{ $t('homepage.nav.getStarted') }}
        </router-link>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import LanguagePicker from "@/components/LanguagePicker.vue";
import ThemeToggle from "@/components/ThemeToggle.vue";

// `sections`: show in-page links to the landing page sections (home page only)
defineProps<{ sections?: boolean }>()

const sectionLinks = [
  { id: 'features', label: 'homepage.nav.features' },
  { id: 'privacy', label: 'homepage.nav.privacy' },
  { id: 'faq', label: 'homepage.nav.faq' },
]

// the page scrolls inside <main>, not the window, so let the browser find the right scroller
function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<style scoped>
.site-header {
  background: color-mix(in srgb, var(--color-background) 82%, transparent);
  backdrop-filter: saturate(1.4) blur(12px);
  -webkit-backdrop-filter: saturate(1.4) blur(12px);
}
.nav-image {
  height: 28px;
  width: 28px;
  border-radius: 25%;
}
</style>
