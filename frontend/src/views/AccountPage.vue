<template>
  <div class="px-5 pt-8 pb-8 sm:px-8">
    <div class="max-w-2xl mx-auto space-y-6">

      <header class="flex items-center justify-between gap-4">
        <h1 class="page-title">{{ $t('accountPage.title') }}</h1>
        <div class="text-ink-soft"><LanguagePicker/></div>
      </header>
      <!-- User Info Section with Inline Edit -->
      <section aria-labelledby="user-info-heading" class="card p-6">
        <h3 id="user-info-heading" class="section-title mb-4">{{ $t('accountPage.userInfo.title') }}</h3>
        <div v-if="authStore.loading && !authStore.user" class="text-center text-ink-soft">
          {{ $t('accountPage.userInfo.loading') }}
        </div>
        <div v-else-if="authStore.user" class="space-y-3">
          <!-- Username Inline Edit -->
          <div>
            <span class="font-medium text-ink-soft">{{ $t('accountPage.userInfo.username') }}</span>
            <span v-if="!editState.username">
  <span class="ml-2 text-ink">{{ authStore.user.username || $t('common.notAvailable') }}</span>
  <button @click="editState.username = true; editForm.username = authStore.user.username"
          class="ml-2 text-primary hover:text-primary">
    <PencilSquareIcon class="h-4 w-4 inline"/>
  </button>
</span>
            <span v-else>
  <input
      v-model="editForm.username"
      class="ml-2 !py-1 !px-2.5 !rounded-lg"
      :disabled="editLoading"
  />
  <button @click="saveField('username')" :disabled="editLoading || !editForm.username"
          class="ml-2 text-success-ink hover:text-success-ink">
    <CheckIcon class="h-4 w-4 inline"/>
  </button>
  <button @click="cancelEdit('username')" :disabled="editLoading"
          class="ml-1 text-ink-soft hover:text-ink-soft">
    <XMarkIcon class="h-4 w-4 inline"/>
  </button>
  <span v-if="editLoading" class="ml-2 text-xs text-ink-soft">...</span>
  <span v-if="editError.username" class="ml-2 text-xs text-danger">{{ editError.username }}</span>
  <span v-else-if="editSuccess.username" class="ml-2 text-xs text-success-ink">
    <CheckCircleIcon class="h-4 w-4 inline"/>
  </span>
</span>
          </div>
          <!-- Email Inline Edit -->
          <div>
            <span class="font-medium text-ink-soft">{{ $t('accountPage.userInfo.email') }}</span>
            <span v-if="!editState.email">
  <span class="ml-2 text-ink">{{ authStore.user.email || $t('common.notAvailable') }}</span>
  <button @click="editState.email = true; editForm.email = authStore.user.email"
          class="ml-2 text-primary hover:text-primary">
    <PencilSquareIcon class="h-4 w-4 inline"/>
  </button>
</span>
            <span v-else>
  <input
      v-model="editForm.email"
      type="email"
      class="ml-2 !py-1 !px-2.5 !rounded-lg"
      :disabled="editLoading"
  />
  <button @click="saveField('email')" :disabled="editLoading || !editForm.email"
          class="ml-2 text-success-ink hover:text-success-ink">
    <CheckIcon class="h-4 w-4 inline"/>
  </button>
  <button @click="cancelEdit('email')" :disabled="editLoading"
          class="ml-1 text-ink-soft hover:text-ink-soft">
    <XMarkIcon class="h-4 w-4 inline"/>
  </button>
  <span v-if="editLoading" class="ml-2 text-xs text-ink-soft">...</span>
  <span v-if="editError.email" class="ml-2 text-xs text-danger">{{ editError.email }}</span>
  <span v-else-if="editSuccess.email" class="ml-2 text-xs text-success-ink">
    <CheckCircleIcon class="h-4 w-4 inline"/>
  </span>
</span>
          </div>
          <div>
            <span class="font-medium text-ink-soft">{{ $t('accountPage.userInfo.memberSince') }}</span>
            <span class="ml-2 text-ink">{{ formattedJoinDate }}</span>
          </div>
        </div>
        <div v-else class="text-center text-danger">
          {{ $t('accountPage.userInfo.error') }}
        </div>
      </section>

      <section aria-labelledby="appearance-heading" class="card p-6">
        <h3 id="appearance-heading" class="section-title mb-1">{{ $t('theme.title') }}</h3>
        <p class="text-ink-soft text-sm mb-4">{{ $t('theme.description') }}</p>
        <div class="inline-flex p-1 rounded-full bg-surface-muted" role="group">
          <button type="button" @click="isDark = false" :aria-pressed="!isDark"
                  :class="['flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors', !isDark ? 'bg-primary-soft text-primary' : 'text-ink-soft']">
            <SunIcon class="h-4 w-4"/> {{ $t('theme.light') }}
          </button>
          <button type="button" @click="isDark = true" :aria-pressed="isDark"
                  :class="['flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors', isDark ? 'bg-primary-soft text-primary' : 'text-ink-soft']">
            <MoonIcon class="h-4 w-4"/> {{ $t('theme.dark') }}
          </button>
        </div>
      </section>

      <section aria-labelledby="change-password-heading" class="card p-6">
        <h3 id="change-password-heading" class="section-title mb-4">
          {{ $t('accountPage.changePassword.title') }}</h3>
        <form @submit.prevent="handleChangePassword" class="space-y-4">
          <div>
            <label for="currentPassword" class="block text-ink-soft text-sm font-medium mb-1.5">{{ $t('accountPage.changePassword.currentPasswordLabel') }}</label>
            <input
                type="password"
                id="currentPassword"
                v-model="passwordData.currentPassword"
                required
                class="w-full"
                autocomplete="current-password"
            >
          </div>
          <div>
            <label for="newPassword" class="block text-ink-soft text-sm font-medium mb-1.5">{{ $t('accountPage.changePassword.newPasswordLabel') }}</label>
            <input
                type="password"
                id="newPassword"
                v-model="passwordData.newPassword"
                required
                minlength="8"
                class="w-full"
                autocomplete="new-password"
            >
            <p v-if="passwordMismatch" class="text-danger text-xs mt-1.5">{{ $t('accountPage.changePassword.passwordMismatch') }}</p>
          </div>
          <div>
            <label for="confirmNewPassword" class="block text-ink-soft text-sm font-medium mb-1.5">{{ $t('accountPage.changePassword.confirmNewPasswordLabel') }}</label>
            <input
                type="password"
                id="confirmNewPassword"
                v-model="passwordData.confirmNewPassword"
                required
                minlength="8"
                class="w-full"
                autocomplete="new-password"
            >
          </div>
          <div v-if="authStore.error" class="text-danger text-sm">{{ authStore.error }}</div>
          <div v-if="successMessage" class="text-success-ink text-sm">{{ successMessage }}</div>
          <button
              type="submit"
              :disabled="authStore.loading || passwordMismatch"
              class="btn btn-primary"
          >
            {{ authStore.loading ? $t('accountPage.changePassword.changing') : $t('accountPage.changePassword.changeButton') }}
          </button>
        </form>
      </section>

      <section aria-labelledby="logout-heading" class="card p-6">
        <h3 id="logout-heading" class="section-title mb-4">{{ $t('accountPage.logout.title') }}</h3>
        <p class="text-ink-soft mb-4">{{ $t('accountPage.logout.description') }}</p>
        <button
            @click="handleLogout"
            :disabled="authStore.loading"
            class="btn btn-secondary"
        >
          {{ authStore.loading ? $t('accountPage.logout.loggingOut') : $t('accountPage.logout.logoutButton') }}
        </button>
      </section>

      <section aria-labelledby="danger-zone-heading" class="rounded-3xl p-6 bg-danger-soft border border-danger/40">
        <h3 id="danger-zone-heading" class="section-title text-danger-ink mb-2">{{ $t('accountPage.dangerZone.title') }}</h3>
        <p class="text-danger-ink mb-4">{{ $t('accountPage.dangerZone.description') }}</p>
        <button
            @click="showDeleteConfirmation = true"
            :disabled="authStore.loading"
            class="btn btn-danger"
        >
          {{ authStore.loading ? $t('accountPage.dangerZone.deleting') : $t('accountPage.dangerZone.deleteButton') }}
        </button>
        <ConfirmationModal
            v-model="showDeleteConfirmation"
            :title="$t('accountPage.dangerZone.confirmDeleteTitle')"
            :message="$t('accountPage.dangerZone.confirmDeleteMessage')"
            :confirm-text="$t('accountPage.dangerZone.confirmDeleteConfirm')"
            :cancel-text="$t('accountPage.dangerZone.confirmDeleteCancel')"
            confirm-button-type="danger"
            @confirm="handleDeleteAccount"
        />
        <div v-if="deleteError" class="text-danger text-sm mt-4">{{ deleteError }}</div>
      </section>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import ConfirmationModal from "@/components/ConfirmationModal.vue";
import LanguagePicker from "@/components/LanguagePicker.vue";
import UserApi from '@/api/users.ts';
import { CheckIcon, CheckCircleIcon, XMarkIcon, PencilSquareIcon, SunIcon, MoonIcon } from '@heroicons/vue/24/outline';
import { useI18n } from 'vue-i18n';
import { useDarkMode } from '@/composables/useDarkMode';
import { formatDay } from '@/utils/formatDate';


interface PasswordData {
  currentPassword: '';
  newPassword: '';
  confirmNewPassword: '';
}

const authStore = useAuthStore();
const { locale } = useI18n();
const { isDark } = useDarkMode();
const router = useRouter();

const editState = reactive({ username: false, email: false });
const editForm = reactive({ username: '', email: '' });
const editLoading = ref(false);
const editError = reactive<{ username?: string; email?: string }>({});
const editSuccess = reactive<{ username?: boolean; email?: boolean }>({});

function cancelEdit(field: 'username' | 'email') {
  editState[field] = false;
  editError[field] = '';
  editSuccess[field] = false;
}

async function saveField(field: 'username' | 'email') {
  editLoading.value = true;
  editError[field] = '';
  editSuccess[field] = false;
  try {
    const payload: Record<string, string> = {};
    payload[field] = editForm[field];

    await UserApi.updateOwnUser(payload);

    // Update local store immediately if needed
    if (authStore.user) {
      authStore.user = { ...authStore.user, ...payload };
    }

    editSuccess[field] = true;
    setTimeout(() => editSuccess[field] = false, 1500);

    editState[field] = false;
  } catch (e: any) {
    editError[field] = e?.response?.data?.message || 'Could not update, please try again.';
  } finally {
    editLoading.value = false;
  }
}


// --- State ---
const passwordData = reactive<PasswordData>({
  currentPassword: '',
  newPassword: '',
  confirmNewPassword: '',
});
const successMessage = ref<string | null>(null); // For password change success
const deleteError = ref<string | null>(null); // Specific error for deletion failure

// --- Computed Properties ---
const passwordMismatch = computed(() => {
  return passwordData.newPassword && passwordData.confirmNewPassword && passwordData.newPassword !== passwordData.confirmNewPassword;
});

// Format join date (example)
const formattedJoinDate = computed(() => {
  if (authStore.user?.created_at) {
    try {
      return formatDay(authStore.user.created_at, locale.value, true) ?? 'Invalid Date';
    } catch (e) {
      return 'Invalid Date';
    }
  }
  return 'N/A';
});

// --- Methods ---

// Handle Password Change Submission
const handleChangePassword = async () => {
  if (passwordMismatch.value) {
    authStore.setError('New passwords do not match.'); // Use store's error handling or a local ref
    return;
  }
  authStore.clearError(); // Clear previous errors
  successMessage.value = null; // Clear previous success message

  try {
    // Assume authStore.changePassword exists and handles API call + state updates
    await authStore.changePassword({
      current_password: passwordData.currentPassword,
      new_password: passwordData.newPassword,
    });

    // If successful (no error thrown by store action):
    successMessage.value = 'Password changed successfully!';
    // Clear form
    passwordData.currentPassword = '';
    passwordData.newPassword = '';
    passwordData.confirmNewPassword = '';

  } catch (error) {
    // Error should be set within the authStore action ideally
    console.error("Password change failed:", error);
    // If the store doesn't set the error message, you might set it here
    if (!authStore.error) {
      authStore.setError('Failed to change password. Please check your current password.');
    }
  }
};

// Handle Logout
const handleLogout = async () => {
  authStore.clearError();
  try {
    await authStore.logout();
    // Redirect to login or home page after logout
    router.push({ name: 'login' }); // Adjust route name if needed
  } catch (error) {
    console.error("Logout failed:", error);
    // Error should be handled/displayed by the store or globally
    if (!authStore.error) {
      authStore.setError('Logout failed. Please try again.');
    }
  }
};

const showDeleteConfirmation = ref(false);

// Handle Account Deletion
const handleDeleteAccount = async () => {
  authStore.clearError();
  deleteError.value = null; // Clear previous delete error

  try {
    // Assume authStore.deleteAccount exists
    await authStore.deleteAccount();
    // Redirect after successful deletion
    alert('Account deleted successfully.'); // Replace with better notification
    router.push({ name: 'home' }); // Or registration page
  } catch (error) {
    console.error("Account deletion failed:", error);
    // Set specific delete error message
    deleteError.value = authStore.error || 'Failed to delete account. Please try again.';
  }
};

// --- Lifecycle Hooks ---
onMounted(() => {
  // Clear any previous errors or success messages when component loads
  authStore.clearError();
  successMessage.value = null;
  deleteError.value = null;

  // Optional: Fetch user data if not already loaded by the store
  // if (!authStore.user) {
  //   authStore.fetchUser(); // Assuming fetchUser exists
  // }
});

</script>

<style scoped>
/* Account page specific styles */
/* Add custom styles here if Tailwind classes are insufficient */

/* Example: Style for the danger zone heading */
#danger-zone-heading {
  /* Additional styles if needed */
}

/* Ensure inputs don't inherit weird browser defaults */
input[type="password"] {
  /* Add specific styles if necessary */
}
</style>