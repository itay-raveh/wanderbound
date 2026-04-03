<script lang="ts" setup>
defineProps<{ progress: number }>();
</script>

<template>
  <div class="progress-track">
    <div class="progress-fill" :style="{ transform: `scaleX(${progress})` }" />
  </div>
</template>

<style lang="scss" scoped>
.progress-track {
  height: 0.25rem;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
}

.progress-fill {
  width: 100%;
  height: 100%;
  border-radius: var(--radius-xs);
  background: var(--q-primary);
  transform-origin: left;
  transition: transform var(--duration-slow) cubic-bezier(0.4, 0, 0.2, 1);
}

:global([dir="rtl"]) .progress-fill {
  transform-origin: right;
}
</style>
