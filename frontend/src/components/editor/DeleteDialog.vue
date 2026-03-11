<script lang="ts" setup>
const show = defineModel<boolean>({ required: true });

defineProps<{
  deleting: boolean;
}>();

defineEmits<{
  confirm: [];
}>();
</script>

<template>
  <q-dialog v-model="show">
    <div class="confirm-dialog">
      <div class="confirm-icon">
        <q-icon name="delete_outline" size="1.5rem" />
      </div>
      <h3 class="confirm-title">Delete all data?</h3>
      <p class="confirm-text">
        This will permanently remove your uploaded data and all albums.
        You'll need to upload again to continue.
      </p>
      <div class="confirm-actions">
        <button v-close-popup class="confirm-btn cancel">Cancel</button>
        <button
          class="confirm-btn danger"
          :disabled="deleting"
          @click="$emit('confirm')"
        >
          {{ deleting ? "Deleting..." : "Delete" }}
        </button>
      </div>
    </div>
  </q-dialog>
</template>

<style lang="scss">
.confirm-dialog {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 1rem;
  padding: 1.75rem;
  max-width: 22rem;
  text-align: center;
}

.confirm-icon {
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 50%;
  background: color-mix(in srgb, var(--danger) 15%, var(--surface));
  color: var(--danger);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1rem;
}

.confirm-title {
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--text-bright);
  margin: 0 0 0.5rem;
}

.confirm-text {
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--text-muted);
  margin: 0 0 1.5rem;
}

.confirm-actions {
  display: flex;
  gap: 0.5rem;
}

.confirm-btn {
  all: unset;
  cursor: pointer;
  flex: 1;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  text-align: center;
  transition: background 0.15s ease, opacity 0.15s ease;
}

.confirm-btn.cancel {
  background: var(--surface);
  color: var(--text);

  &:hover {
    background: var(--border-color);
  }
}

.confirm-btn.danger {
  background: var(--danger);
  color: white;

  &:hover {
    opacity: 0.9;
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}
</style>
