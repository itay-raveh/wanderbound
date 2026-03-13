<script lang="ts" setup>
import { matWarning } from "@quasar/extras/material-icons";

defineProps<{
  reason: string | null;
}>();
</script>

<template>
  <div class="banner">
    <div class="banner-header">
      <q-icon :name="matWarning" size="sm" class="banner-icon" />
      <span class="text-subtitle1 banner-title">Browser not supported</span>
    </div>
    <p class="text-body2 banner-text">
      Switch to a recent browser:
      <strong>Chrome</strong>, <strong>Firefox</strong>,
      <strong>Safari</strong>, or <strong>Edge</strong>.
    </p>
    <span v-if="reason" class="text-caption banner-reason">{{ reason }}</span>
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
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.375rem;
}

.banner-icon {
  color: var(--danger);
  flex-shrink: 0;
}

.banner-title {
  color: var(--text-bright);
}

.banner-text {
  line-height: 1.6;
  color: var(--text-muted);
  margin: 0;
}

.banner-text strong {
  color: var(--text);
  font-weight: 600;
}

.banner-reason {
  display: block;
  color: var(--text-faint);
  margin-top: 0.25rem;
}
</style>
