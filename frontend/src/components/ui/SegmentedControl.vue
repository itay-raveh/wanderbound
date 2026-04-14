<script lang="ts" setup generic="T extends string | number | boolean">
defineProps<{
  modelValue: T;
  options: { label: string; value: T; icon?: string }[];
  compact?: boolean;
  ariaLabel?: string;
}>();

defineEmits<{
  "update:modelValue": [value: T];
}>();
</script>

<template>
  <div class="seg-track" :class="{ compact }" role="group" :aria-label="ariaLabel">
    <button
      v-for="option in options"
      :key="String(option.value)"
      class="seg-btn"
      :class="{ active: option.value === modelValue }"
      :aria-pressed="option.value === modelValue"
      @click="option.value !== modelValue && $emit('update:modelValue', option.value)"
    >
      <q-icon v-if="option.icon" :name="option.icon" size="var(--type-sm)" />
      {{ option.label }}
    </button>
  </div>
</template>

<style lang="scss" scoped>
.seg-track {
  display: flex;
  gap: var(--gap-xs);
  padding: var(--gap-xs);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--text) 8%, var(--bg-secondary));
}

.seg-btn {
  all: unset;
  cursor: pointer;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-sm);
  padding: var(--gap-sm-md) var(--gap-md-lg);
  border-radius: var(--radius-sm);
  font-size: var(--type-sm);
  font-weight: 500;
  color: var(--text-muted);
  transition: background var(--duration-fast) ease, color var(--duration-fast) ease, box-shadow var(--duration-fast) ease;

  &:hover:not(.active) {
    color: var(--text);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 1px;
  }

  &.active {
    background: var(--bg-secondary);
    color: var(--text-bright);
    box-shadow: var(--shadow-sm);
  }
}

.seg-track.compact {
  width: 6rem;
  flex-shrink: 0;

  .seg-btn {
    padding: var(--gap-sm-md) var(--gap-md);
    font-weight: 600;
  }
}

@media (prefers-reduced-motion: reduce) {
  .seg-btn {
    transition: none;
  }
}
</style>
