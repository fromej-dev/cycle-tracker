<template>
  <div class="relative" ref="dropdownContainer">
    <button
        @click="toggleDropdown"
        class="flex items-center p-2 rounded-xl text-current hover:bg-black/10 focus:outline-none focus:ring-2 focus:ring-white transition duration-150 ease-in-out"
        aria-haspopup="true"
        :aria-expanded="isOpen"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
      </svg>
      <span class="text-sm font-medium uppercase">{{ currentLocale }}</span>
      <svg class="h-4 w-4 ml-1 transition-transform duration-200" :class="{ 'transform rotate-180': isOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
      </svg>
    </button>

    <transition
        enter-active-class="transition ease-out duration-100"
        enter-from-class="transform opacity-0 scale-95"
        enter-to-class="transform opacity-100 scale-100"
        leave-active-class="transition ease-in duration-75"
        leave-from-class="transform opacity-100 scale-100"
        leave-to-class="transform opacity-0 scale-95"
    >
      <div
          v-if="isOpen"
          class="absolute right-0 mt-2 w-40 origin-top-right bg-surface text-ink rounded-2xl shadow-lg ring-1 ring-line focus:outline-none z-50"
          role="menu"
          aria-orientation="vertical"
          aria-labelledby="menu-button"
          tabindex="-1"
      >
        <div class="py-1" role="none">
          <button
              v-for="lang in availableLocales"
              :key="lang"
              @click="changeLanguage(lang)"
              :class="[
              'block w-full text-left px-4 py-2 text-sm',
              lang === currentLocale ? 'bg-primary-soft text-primary font-semibold' : 'text-ink-soft hover:bg-surface-muted hover:text-ink'
            ]"
              role="menuitem"
              tabindex="-1"
              :id="'menu-item-' + lang"
          >
            {{ getLanguageDisplayName(lang) }} </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { onClickOutside } from '@vueuse/core'; // Using VueUse for click outside

// --- Configuration for Language Display Names ---
// You can customize this map based on your supported languages
const languageDisplayNames: Record<string, string> = {
  en: 'English',
  es: 'Español',
  fr: 'Français',
  de: 'Deutsch',
  nl: 'Nederlands'
  // Add other languages your app supports
};

// --- i18n ---
const { locale, availableLocales } = useI18n();

// --- Dropdown State ---
const isOpen = ref(false);
const dropdownContainer = ref(null); // Template ref for click outside

// --- Computed Properties ---
const currentLocale = computed(() => locale.value);

// --- Methods ---
const toggleDropdown = () => {
  isOpen.value = !isOpen.value;
};

const closeDropdown = () => {
  isOpen.value = false;
};

const changeLanguage = (lang: string) => {
  if (locale.value !== lang) {
    locale.value = lang;
    // Optional: Persist preference (e.g., localStorage)
    localStorage.setItem('user-locale', lang);
  }
  closeDropdown();
};

const getLanguageDisplayName = (langCode: string): string => {
  return languageDisplayNames[langCode] || langCode.toUpperCase(); // Fallback to uppercase code
};

// --- Click Outside Handling (using @vueuse/core) ---
onClickOutside(dropdownContainer, closeDropdown);

</script>

<style scoped>
/* Add any minor scoped styles if absolutely necessary, */
/* but prefer Tailwind utility classes.               */

/* Example: Ensure SVGs inherit text color */
button svg {
  stroke: currentColor;
}

</style>