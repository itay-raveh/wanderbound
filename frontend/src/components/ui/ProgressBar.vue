<script lang="ts" setup>
defineProps<{ progress: number }>();
</script>

<template>
  <div
    class="progress-track"
    role="progressbar"
    :aria-valuenow="Math.round(progress * 100)"
    aria-valuemin="0"
    aria-valuemax="100"
  >
    <div class="progress-fill" :style="{ transform: `scaleX(${progress})` }" />
  </div>
</template>

<style lang="scss" scoped>
.progress-track {
  height: 0.25rem;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  overflow: hidden;
}

.progress-fill {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: var(--radius-xs);
  background: var(--q-primary);
  transform-origin: left;
  transition: transform var(--duration-slow) cubic-bezier(0.4, 0, 0.2, 1);
}

.progress-fill::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--text-bright) 20%, transparent),
    transparent
  );
  animation: shimmer 2s ease-in-out infinite;
}

:dir(rtl) .progress-fill {
  transform-origin: right;
}

@keyframes shimmer {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(100%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .progress-fill::after {
    animation: none;
  }
}
</style>
