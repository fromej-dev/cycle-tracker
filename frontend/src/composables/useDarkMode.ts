import { useDark, useToggle } from '@vueuse/core'

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
