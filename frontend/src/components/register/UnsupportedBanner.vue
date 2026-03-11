<script lang="ts" setup>
defineProps<{
  reason: string | null;
}>();
</script>

<template>
  <div class="banner">
    <div class="banner-header">
      <q-icon name="warning" size="sm" class="banner-icon" />
      <span class="banner-title">Browser not supported</span>
    </div>
    <p class="banner-text">
      Switch to a recent browser:
      <strong>Chrome</strong>, <strong>Firefox</strong>,
      <strong>Safari</strong>, or <strong>Edge</strong>.
    </p>
    <span v-if="reason" class="banner-reason">{{ reason }}</span>
  </div>
</template>

<style scoped>
.banner {
  padding: 1rem 1.25rem;
  border-radius: 0.625rem;
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
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text-bright);
}

.banner-text {
  font-size: 0.8125rem;
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
  font-size: 0.75rem;
  color: var(--text-faint);
  margin-top: 0.25rem;
}
</style>
