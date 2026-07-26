<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import {
  symOutlinedAdd,
  symOutlinedMap,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

defineEmits<{
  addMap: [];
}>();
</script>

<template>
  <button type="button" class="nav-chip" @click="$emit('addMap')">
    <q-icon :name="symOutlinedMap" size="var(--type-xs)" />
    <span>{{ t("nav.addMap") }}</span>
    <q-icon :name="symOutlinedAdd" size="var(--type-xs)" />
  </button>
</template>

<style lang="scss" scoped>
.nav-chip {
  appearance: none;
  display: flex;
  align-items: center;
  gap: var(--gap-xs);
  padding: var(--gap-xs) var(--gap-sm);
  border: 1px solid color-mix(in srgb, var(--border-color) 70%, transparent);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: var(--type-xs);
  cursor: pointer;
  transition:
    color var(--duration-fast),
    background var(--duration-fast),
    border-color var(--duration-fast);

  &:hover {
    color: var(--text);
    background: color-mix(in srgb, var(--text) 4%, transparent);
    border-color: var(--border-color);
  }

  &:active {
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
    border-color: color-mix(in srgb, var(--q-primary) 45%, transparent);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 1px;
  }
}

@media (pointer: coarse) {
  .nav-chip {
    padding: var(--gap-sm) var(--gap-sm-md);
  }
}

@media (prefers-reduced-motion: reduce) {
  .nav-chip {
    transition: none;
  }
}
</style>
