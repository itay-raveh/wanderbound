<script lang="ts" setup>
import ProgressBar from "./ProgressBar.vue";
import {
  symOutlinedClose,
  symOutlinedCheck,
} from "@quasar/extras/material-symbols-outlined";

defineProps<{
  state: "idle" | "running" | "done";
  idleIcon: string;
  idleLabel: string;
  progressFraction: number;
  progressMessage: string;
  doneMessage: string;
}>();

defineEmits<{ start: []; cancel: [] }>();
</script>

<template>
  <div
    v-if="state === 'done'"
    role="status"
    aria-live="polite"
    class="action-btn done"
    :aria-label="doneMessage"
  >
    <q-icon :name="symOutlinedCheck" size="var(--type-lg)" class="done-icon" />
    {{ doneMessage }}
  </div>

  <button
    v-else-if="state === 'running'"
    class="action-btn running"
    :aria-label="progressMessage"
    aria-busy="true"
    @click="$emit('cancel')"
  >
    <div class="progress-content">
      <q-icon
        :name="symOutlinedClose"
        size="var(--type-md)"
        class="cancel-icon"
      />
      <span class="progress-text" aria-live="polite">{{ progressMessage }}</span>
    </div>
    <ProgressBar :progress="progressFraction" />
  </button>

  <button
    v-else
    class="action-btn"
    :aria-label="idleLabel"
    @click="$emit('start')"
  >
    <q-icon :name="idleIcon" size="var(--type-lg)" />
    {{ idleLabel }}
  </button>
</template>

<style lang="scss" scoped>
@use "@/styles/action-button" as *;
@include action-button;

.action-btn.running {
  border-color: var(--border-color);
  color: var(--text-muted);
  cursor: pointer;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: var(--gap-xs);
  min-width: 10rem;

  &:hover {
    border-color: var(--text-faint);

    .cancel-icon {
      color: var(--text);
    }
  }
}

.progress-content {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}

.cancel-icon {
  color: var(--text-faint);
  transition: color var(--duration-fast);
}

.progress-text {
  font-size: var(--type-xs);
  font-variant-numeric: tabular-nums;
}

.action-btn.done {
  border-color: var(--q-primary);
  color: var(--q-primary);
  cursor: default;
  animation: fade-out 0.4s ease 2.5s forwards;
}

.done-icon {
  animation: scale-in var(--duration-normal) cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes scale-in {
  from {
    transform: scale(0);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes fade-out {
  to {
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .done-icon {
    animation: none;
  }

  .action-btn.done {
    animation: none;
  }
}
</style>
