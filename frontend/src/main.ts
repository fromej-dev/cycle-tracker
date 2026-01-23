import './assets/css/main.css' // Import Tailwind CSS

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from '@/router'
import i18n from '@/i18n'
import Toast from 'vue-toastification'
import 'vue-toastification/dist/index.css'
import './assets/css/toast.css' // Custom toast styles

// Initialize Axios with configuration
import '@/api/index.ts' // This runs the code in api/index.js

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
app.use(router)
app.use(i18n)
app.use(Toast, toastOptions)

// Initialize auth state from local storage
import { useAuthStore } from './stores/auth'
const authStore = useAuthStore()
authStore.initializeAuth() // Call this action

app.mount('#app')