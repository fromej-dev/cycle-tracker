import './assets/css/main.css' // Import Tailwind CSS

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from '@/router'
import i18n from '@/i18n'
import Toast from 'vue-toastification'
import 'vue-toastification/dist/index.css'
import './assets/css/toast.css' // Custom toast styles
import { initTheme } from '@/composables/useDarkMode'

// Initialize Axios with configuration
import '@/api/index.ts' // This runs the code in api/index.js

initTheme() // theme must be live on every device, not only where ThemeToggle is rendered

const app = createApp(App)

// Toast options
const toastOptions = {
  position: 'top-right',
  timeout: 3000,
  closeOnClick: true,
  pauseOnFocusLoss: true,
  pauseOnHover: true,
  draggable: true,
  draggablePercent: 0.6,
  showCloseButtonOnHover: false,
  hideProgressBar: false,
  closeButton: 'button',
  icon: true,
  rtl: false,
}

app.use(createPinia())
// restore auth BEFORE the router's first navigation, otherwise a reload on /account bounces to /dashboard
import { useAuthStore } from './stores/auth'
useAuthStore().initializeAuth()
app.use(router)
app.use(i18n)
app.use(Toast, toastOptions)


app.mount('#app')