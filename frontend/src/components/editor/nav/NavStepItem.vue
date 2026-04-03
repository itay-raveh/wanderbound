<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import {
  symOutlinedVisibility,
  symOutlinedVisibilityOff,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

defineProps<{
  name: string;
  date: string;
  thumb: string | null;
  color: string;
  active: boolean;
  excluded: boolean;
}>();

defineEmits<{
  click: [];
  toggle: [];
}>();
</script>

<template>
  <div
    role="button"
    tabindex="0"
    :class="['nav-item', { visible: active, excluded }]"
    :aria-current="active ? 'step' : undefined"
    @click="$emit('click')"
    @keydown.enter="$emit('click')"
  >
    <div class="item-thumb">
      <img v-if="thumb" :src="thumb" alt="" width="36" height="28" class="thumb-img" loading="lazy" />
      <div v-else class="thumb-empty" :style="{ background: color }" />
    </div>
    <div class="item-info">
      <span class="item-name" dir="auto">{{ name }}</span>
      <span class="item-date text-muted">{{ date }}</span>
    </div>
    <button
      type="button"
      class="step-toggle"
      :aria-label="excluded ? t('nav.showStep') : t('nav.hideStep')"
      @click.stop="$emit('toggle')"
    >
      <q-icon :name="excluded ? symOutlinedVisibilityOff : symOutlinedVisibility" size="var(--type-xs)" />
      <q-tooltip>{{ excluded ? t("nav.showStep") : t("nav.hideStep") }}</q-tooltip>
    </button>
  </div>
</template>

<style lang="scss" scoped>
@use "nav-item";

.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-empty {
  width: 100%;
  height: 100%;
  opacity: var(--opacity-thumb-empty);
}

.item-date {
  font-size: var(--type-xs);
}

.step-toggle {
  appearance: none;
  background: none;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
  padding: var(--gap-sm);
  border-radius: var(--radius-sm);
  color: var(--text-faint);
  opacity: var(--opacity-toggle-idle);
  transition: opacity var(--duration-fast), color var(--duration-fast), background var(--duration-fast);

  .nav-item:hover & {
    opacity: 1;
  }

  .nav-item &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
  }

  .nav-item &:active {
    background: color-mix(in srgb, var(--q-primary) 16%, transparent);
  }

  .nav-item.excluded & {
    opacity: 1;
  }

  &:focus-visible {
    opacity: 1;
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

@media (hover: none) {
  .step-toggle {
    opacity: 1;
  }
}

@media (pointer: coarse) {
  .step-toggle {
    min-width: 2.75rem;
    min-height: 2.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--gap-md-lg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .step-toggle {
    transition: none;
  }
}
</style>
