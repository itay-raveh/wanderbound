<script lang="ts" setup>
defineProps<{
  number: number;
}>();
</script>

<template>
  <div class="step">
    <div class="row no-wrap items-center q-gutter-x-sm q-mb-sm">
      <div class="step-number flex flex-center text-caption text-weight-bold text-primary">{{ number }}</div>
      <div class="text-h6 text-weight-semibold text-bright"><slot name="title" /></div>
    </div>
    <div class="step-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.step-number {
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  flex-shrink: 0;
}

.step-body {
  padding-left: 2.125rem;
  padding-right: 2.125rem;
}

@media (max-width: 479px) {
  .step-body {
    padding-left: 0;
    padding-right: 0;
  }
}
</style>
