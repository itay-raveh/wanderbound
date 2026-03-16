<script lang="ts" setup>
import { matWarning } from "@quasar/extras/material-icons";

defineProps<{
  reason: string | null;
}>();
</script>

<template>
  <div class="banner">
    <div class="banner-header row no-wrap items-center q-gutter-x-sm">
      <q-icon :name="matWarning" size="sm" class="text-danger" />
      <span class="text-subtitle1 text-bright">Browser not supported</span>
    </div>
    <p class="text-body2 text-muted no-margin">
      Switch to a recent browser:
      <strong>Chrome</strong>, <strong>Firefox</strong>,
      <strong>Safari</strong>, or <strong>Edge</strong>.
    </p>
    <span v-if="reason" class="text-caption block q-mt-xs text-faint">{{ reason }}</span>
  </div>
</template>

<style scoped>
.banner {
  padding: 1rem 1.25rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--danger);
  background: color-mix(in srgb, var(--danger) 6%, var(--bg-secondary));
}

.banner-header {
  margin-bottom: 0.375rem;
}

.banner strong {
  color: var(--text);
}
</style>
