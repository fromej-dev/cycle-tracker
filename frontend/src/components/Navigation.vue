<template>
  <template v-if="isAuthenticated">

    <div v-if="!isMobile"
         :class="[
            'h-screen flex flex-col flex-shrink-0 bg-white dark:bg-gray-800 border-r border-gray-100 dark:border-gray-700 transition-width duration-300 ease-in-out',
            sidebarOpen ? 'w-60' : 'w-20'
         ]">
      <div class="flex-shrink-0 flex items-center h-16 border-b border-gray-100 dark:border-gray-700 px-4" :class="[sidebarOpen ? 'justify-between' : 'justify-center']">
         <span v-if="sidebarOpen">
          <router-link :to="{ name: 'dashboard' }" class="text-l flex gap-2 items-center font-bold text-primary">
            <img src="/assets/icons/180_tp.png" alt="Period Tracker" class="nav-image">
            {{ $t('common.title')}}
          </router-link>
         </span>
        <div class="flex items-center gap-1">
          <ThemeToggle />
          <button @click="toggleSidebar" class="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary">
            <ChevronDoubleLeftIcon v-if="sidebarOpen" class="h-5 w-5 text-gray-600 dark:text-gray-300" />
            <ChevronDoubleRightIcon v-else class="h-5 w-5 text-gray-600 dark:text-gray-300" />
          </button>
        </div>
      </div>

      <nav class="flex-1 flex flex-col mt-4 px-2 space-y-2 overflow-y-auto pb-4">
        <RouterLink
            v-for="item in navigationItems"
            :key="item.name"
            :to="item.to"
            custom
            v-slot="{ href, navigate, isActive }"
        >
          <a
              :href="href"
              @click="navigate"
              :class="[
                    'flex items-center px-4 py-2.5 rounded-lg transition-colors duration-150 group',
                    isActive ? 'bg-primary-50 dark:bg-gray-700 text-primary dark:text-primary font-medium' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-gray-100',
                    sidebarOpen ? 'justify-start' : 'justify-center'
                ]"
              :title="sidebarOpen ? '' : item.name"
          >
            <component :is="item.icon" :class="['h-5 w-5 flex-shrink-0', isActive ? 'text-primary' : 'text-gray-400 group-hover:text-gray-500']" aria-hidden="true" />
            <span v-if="sidebarOpen" class="ml-3 text-sm">{{ item.name }}</span>
          </a>
        </RouterLink>
      </nav>
    </div>

    <nav v-else class="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-800 border-t border-gray-100 dark:border-gray-700 flex justify-around py-2 shadow-[0_-2px_10px_-3px_rgba(0,0,0,0.05)] dark:shadow-[0_-2px_10px_-3px_rgba(0,0,0,0.3)] z-50">
      <RouterLink
          v-for="item in navigationItems"
          :key="item.name"
          :to="item.to"
          custom
          v-slot="{ href, navigate, isActive }"
      >
        <a
            :href="href"
            @click="navigate"
            :class="[
                'flex flex-col items-center text-xs px-2 py-1 rounded-md w-16',
                isActive ? 'text-primary font-medium' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            ]"
        >
          <component :is="item.icon" :class="['h-5 w-5 mb-0.5']" aria-hidden="true" />
          <span>{{ item.name }}</span>
        </a>
      </RouterLink>
    </nav>

  </template>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { RouterLink } from 'vue-router';
import {
  HomeIcon,
  UserCircleIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
} from '@heroicons/vue/24/outline';
import ThemeToggle from '@/components/ThemeToggle.vue';

interface Props {
  isMobile: boolean;
  isAuthenticated: boolean;
}
// Default values can be useful, although App.vue will always pass them
const props = withDefaults(defineProps<Props>(), {
  isMobile: false,
  isAuthenticated: false,
});

const sidebarOpen = ref<boolean>(true); // Default state for desktop sidebar

// Navigation items - adjusted home link potentially if needed based on auth logic elsewhere
const navigationItems = ref([
  // Consider if 'Home' is needed for authenticated users, maybe Dashboard is the default?
  // { name: 'Home', to: '/', icon: HomeIcon },
  { name: 'Dashboard', to: '/dashboard', icon: HomeIcon },
  { name: 'Account', to: '/account', icon: UserCircleIcon },
]);

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value;
}
</script>

<style scoped>
/* Styles remain largely the same, ensuring they target the correct elements */
.transition-width {
  transition-property: width;
}

.bg-primary-50 {
  background-color: #FFF1F2; /* Example Pink-50 */
}

.focus\:ring-primary:focus {
  --tw-ring-color: #E11D48; /* Example primary color */
}

.nav-image {
  height: 27px;
  width: 27px;
  background: #fff; /* Assuming white background */
  border-radius: 25%;
  padding: 3px;
}

/* Optional: Style scrollbar within the sidebar nav */
nav::-webkit-scrollbar {
  width: 6px;
}
nav::-webkit-scrollbar-thumb {
  background-color: rgba(0,0,0,0.2);
  border-radius: 3px;
}
nav::-webkit-scrollbar-track {
  background: rgba(0,0,0,0.05);
}
</style>