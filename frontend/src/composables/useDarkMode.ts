import { useDark, useToggle } from '@vueuse/core'
import { watch } from 'vue'

// Keep in sync with --color-background in main.css (light / dark)
const THEME_COLORS = { light: '#FAF6F2', dark: '#17121A' }

export function useDarkMode() {
  const isDark = useDark({
    selector: 'html',
    attribute: 'class',
    valueDark: 'dark',
    valueLight: '',
    storageKey: 'cycle-tracker-theme',
    storage: localStorage,
  })

  const toggleDark = useToggle(isDark)

  return {
    isDark,
    toggleDark,
  }
}

/** Call once at app level so phones (no desktop sidebar toggle) get the saved / system theme. */
export function initTheme() {
  const { isDark } = useDarkMode()
  watch(
    isDark,
    (dark) => {
      const meta = document.querySelector('meta[name="theme-color"]')
      meta?.setAttribute('content', dark ? THEME_COLORS.dark : THEME_COLORS.light)
    },
    { immediate: true },
  )
}
