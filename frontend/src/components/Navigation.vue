<template>
  <template v-if="isAuthenticated">

    <!-- Desktop / tablet sidebar -->
    <div v-if="!isMobile"
         :class="[
            'h-dvh flex flex-col flex-shrink-0 bg-surface border-r border-line transition-[width] duration-300 ease-in-out',
            sidebarOpen ? 'w-60' : 'w-20'
         ]">
      <div class="flex-shrink-0 flex items-center h-16 border-b border-line px-4" :class="[sidebarOpen ? 'justify-between' : 'justify-center']">
         <span v-if="sidebarOpen">
          <router-link :to="{ name: 'dashboard' }" class="flex gap-2.5 items-center font-display text-lg text-primary">
            <img src="/assets/icons/180_tp.png" alt="" class="nav-image">
            {{ $t('common.title')}}
          </router-link>
         </span>
        <div class="flex items-center gap-1">
          <ThemeToggle />
          <button @click="toggleSidebar" class="p-2 rounded-xl text-ink-soft hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
            <ChevronDoubleLeftIcon v-if="sidebarOpen" class="h-5 w-5" />
            <ChevronDoubleRightIcon v-else class="h-5 w-5" />
          </button>
        </div>
      </div>

      <nav class="flex-1 flex flex-col mt-4 px-3 space-y-1 overflow-y-auto pb-4">
        <RouterLink
            v-for="item in navigationItems"
            :key="item.key"
            :to="item.to"
            custom
            v-slot="{ href, navigate, isActive }"
        >
          <a
              :href="href"
              @click="navigate"
              :class="[
                    'flex items-center px-4 py-2.5 rounded-xl transition-colors duration-150',
                    isActive ? 'bg-primary-soft text-primary font-semibold' : 'text-ink-soft hover:bg-surface-muted hover:text-ink',
                    sidebarOpen ? 'justify-start' : 'justify-center'
                ]"
              :title="sidebarOpen ? '' : $t(item.label)"
          >
            <component :is="isActive ? item.iconActive : item.icon" class="h-5 w-5 flex-shrink-0" aria-hidden="true" />
            <span v-if="sidebarOpen" class="ml-3 text-sm">{{ $t(item.label) }}</span>
          </a>
        </RouterLink>
      </nav>
    </div>

    <!-- Mobile tab bar -->
    <nav v-else class="tabbar fixed bottom-0 left-0 right-0 z-50 border-t border-line flex justify-around px-4 pt-2">
      <RouterLink
          v-for="item in navigationItems"
          :key="item.key"
          :to="item.to"
          custom
          v-slot="{ href, navigate, isActive }"
      >
        <a
            :href="href"
            @click="navigate"
            :aria-current="isActive ? 'page' : undefined"
            :class="[
                'flex flex-col items-center gap-0.5 text-xs flex-1 max-w-32 py-1 rounded-xl',
                isActive ? 'text-primary font-semibold' : 'text-ink-soft'
            ]"
        >
          <span :class="['flex items-center justify-center h-8 w-14 rounded-full transition-colors', isActive ? 'bg-primary-soft' : '']">
            <component :is="isActive ? item.iconActive : item.icon" class="h-6 w-6" aria-hidden="true" />
          </span>
          <span>{{ $t(item.label) }}</span>
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
  CalendarDaysIcon,
  CalendarDateRangeIcon,
  UserCircleIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
} from '@heroicons/vue/24/outline';
import { CalendarDateRangeIcon as PlanSolid, CalendarDaysIcon as CalendarSolid, HomeIcon as HomeSolid, UserCircleIcon as UserCircleSolid } from '@heroicons/vue/24/solid';
import ThemeToggle from '@/components/ThemeToggle.vue';

interface Props {
  isMobile: boolean;
  isAuthenticated: boolean;
}
const props = withDefaults(defineProps<Props>(), {
  isMobile: false,
  isAuthenticated: false,
});

const sidebarOpen = ref<boolean>(true);

const navigationItems = [
  { key: 'dashboard', label: 'nav.dashboard', to: '/dashboard', icon: HomeIcon, iconActive: HomeSolid },
  { key: 'calendar', label: 'nav.calendar', to: '/calendar', icon: CalendarDaysIcon, iconActive: CalendarSolid },
  { key: 'plan', label: 'nav.plan', to: '/plan', icon: CalendarDateRangeIcon, iconActive: PlanSolid },
  { key: 'account', label: 'nav.account', to: '/account', icon: UserCircleIcon, iconActive: UserCircleSolid },
];

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value;
}
</script>

<style scoped>
.tabbar {
  background: var(--color-surface);
  box-shadow: var(--shadow-nav);
  padding-bottom: calc(0.5rem + env(safe-area-inset-bottom));
}

.nav-image {
  height: 28px;
  width: 28px;
  border-radius: 25%;
}
</style>
