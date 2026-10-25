<template>
  <Transition name="modal-fade">
    <div
        v-if="modelValue"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
        @click.self="handleCancel"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="modalTitleId"
        :aria-describedby="modalDescriptionId"
    >
      <div class="bg-surface rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
        <div class="px-6 py-4 border-b border-line">
          <h3 :id="modalTitleId" class="text-lg font-semibold text-ink">
            <slot name="title">{{ title }}</slot>
          </h3>
        </div>

        <div class="px-6 py-5">
          <p :id="modalDescriptionId" class="text-sm text-ink-soft">
            <slot name="message">{{ message }}</slot>
          </p>
        </div>

        <div class="px-6 py-4 bg-surface-muted border-t border-line flex justify-end space-x-3">
          <button
              @click="handleCancel"
              type="button"
              class="px-4 py-2 rounded-xl border border-line-strong bg-surface text-sm font-medium text-ink-soft hover:bg-surface-muted focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary"
          >
            {{ cancelText }}
          </button>
          <button
              @click="handleConfirm"
              type="button"
              :class="[
              'px-4 py-2 rounded-xl border border-transparent text-sm font-medium shadow-card focus:outline-none focus:ring-2 focus:ring-offset-2',
              confirmButtonClass // Apply dynamic styling based on type
            ]"
          >
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import { useI18n} from "vue-i18n";

const {t} = useI18n()
// --- Props ---

interface Props {
  modelValue: boolean; // Controls visibility (use with v-model)
  title?: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  confirmButtonType?: 'primary' | 'danger' | 'warning'; // For styling confirm button
  closeOnOverlayClick?: boolean; // Whether clicking the background closes the modal
}

// Define props with defaults
const props = withDefaults(defineProps<Props>(), {
  modelValue: false,
  title: 'Confirm Action',
  message: 'Are you sure you want to proceed?',
  confirmText: 'Confirm',
  cancelText: 'Cancel',
  confirmButtonType: 'primary', // Default style
  closeOnOverlayClick: true, // Default to closable on overlay click
});

// --- Emits ---

// Define the events the component can emit
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void; // For v-model support
  (e: 'confirm'): void;
  (e: 'cancel'): void;
}>();

// --- State ---

// Generate unique IDs for ARIA attributes
const modalId = `modal-${Math.random().toString(36).substring(2, 9)}`;
const modalTitleId = `${modalId}-title`;
const modalDescriptionId = `${modalId}-description`;

// --- Computed Properties ---

// Determine the confirm button's CSS classes based on the type prop
const confirmButtonClass = computed(() => {
  switch (props.confirmButtonType) {
    case 'danger':
      return 'bg-danger text-surface hover:brightness-90 focus:ring-danger';
    case 'warning':
      return 'bg-luteal text-on-phase hover:brightness-90 focus:ring-luteal';
    case 'primary':
    default:
      // Assuming 'primary' is defined in your Tailwind config or global styles
      // Fallback to a common blue/indigo if not
      return 'bg-primary text-on-primary hover:bg-primary-hover focus:ring-primary disabled:opacity-50'; // Use your primary/secondary colors
      // return 'bg-indigo-600 hover:bg-indigo-700 focus:ring-primary'; // Alternative default
  }
});

// --- Methods ---

// Handle confirm action
const handleConfirm = () => {
  emit('confirm');
  closeModal(); // Close modal after confirmation
};

// Handle cancel action
const handleCancel = () => {
  // Only close on overlay click if the prop allows it
  // Check if the event target is the overlay itself
  // This check might need refinement depending on exact structure/events
  // For simplicity, we'll rely on the .self modifier on the overlay click handler for now
  // if (event && event.target !== event.currentTarget && !props.closeOnOverlayClick) {
  //   return; // Click was inside the modal content, not the overlay itself
  // }

  emit('cancel');
  closeModal();
};

// Close the modal by emitting update event for v-model
const closeModal = () => {
  emit('update:modelValue', false);
};

// Handle Escape key press to close modal
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.modelValue) {
    handleCancel();
  }
};

// --- Watchers ---

// Add/remove Escape key listener based on modal visibility
watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    document.addEventListener('keydown', handleKeydown);
  } else {
    document.removeEventListener('keydown', handleKeydown);
  }
}, { immediate: true }); // Run immediately to add listener if modal starts open

// Cleanup listener on unmount (though watch usually handles this)
import { onUnmounted } from 'vue';
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown);
});

</script>

<style scoped>
/* Fade Transition for Modal */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

/* Optional: Add a subtle scale effect */
.modal-fade-enter-active .bg-surface,
.modal-fade-leave-active .bg-surface {
  transition: all 0.3s ease;
}
.modal-fade-enter-from .bg-surface,
.modal-fade-leave-to .bg-surface {
  transform: scale(0.95);
  opacity: 0;
}
</style>