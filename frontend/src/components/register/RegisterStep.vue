<script lang="ts" setup>
defineProps<{
  number: number;
}>();
</script>

<template>
  <div class="step">
    <div class="step-header">
      <div class="step-number text-caption">{{ number }}</div>
      <div class="step-title text-h6"><slot name="title" /></div>
    </div>
    <div class="step-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.step-header {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  margin-bottom: 0.625rem;
}

.step-number {
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  color: var(--q-primary);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-title {
  font-weight: 600;
  color: var(--text-bright);
}

.step-title :deep(strong) {
  color: var(--text-bright);
}

.step-body {
  padding-left: 2.125rem;
  padding-right: 2.125rem;
}
</style>
