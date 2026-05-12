import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'campus_theme'

function applyHtmlClass(isDark) {
  const root = document.documentElement
  if (isDark) root.classList.add('dark')
  else root.classList.remove('dark')
}

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(
    typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY) === 'dark',
  )

  function toggle() {
    isDark.value = !isDark.value
    localStorage.setItem(STORAGE_KEY, isDark.value ? 'dark' : 'light')
    applyHtmlClass(isDark.value)
  }

  /**与 index.html 内联脚本一致，供需要时同步 */
  function syncFromStorage() {
    const dark = localStorage.getItem(STORAGE_KEY) === 'dark'
    isDark.value = dark
    applyHtmlClass(dark)
  }

  return { isDark, toggle, syncFromStorage }
})
