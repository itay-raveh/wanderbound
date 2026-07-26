<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import { symOutlinedAdd } from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

defineEmits<{
  addMap: [];
}>();
</script>

<template>
  <button type="button" class="nav-add-map" @click="$emit('addMap')">
    <q-icon :name="symOutlinedAdd" size="var(--type-sm)" />
    <span>{{ t("nav.addMap") }}</span>
  </button>
</template>

<style lang="scss" scoped>
.nav-add-map {
  appearance: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-sm);
  width: 100%;
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-bright);
  font-family: var(--font-ui);
  font-size: var(--type-sm);
  font-weight: 600;
  cursor: pointer;
  transition:
    color var(--duration-fast),
    background var(--duration-fast),
    border-color var(--duration-fast);

  &:hover {
    background: color-mix(in srgb, var(--q-primary) 8%, var(--surface));
    border-color: color-mix(in srgb, var(--q-primary) 55%, var(--border-color));
    color: var(--primary-text);
  }

  &:active {
    background: color-mix(in srgb, var(--q-primary) 13%, var(--surface));
    border-color: var(--q-primary);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 1px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .nav-add-map {
    transition: none;
  }
}
</style>
