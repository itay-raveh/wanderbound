<script lang="ts" setup>
import type { DateRange } from "@/client";
import { useI18n } from "vue-i18n";
import {
  symOutlinedMap,
  symOutlinedClose,
  symOutlinedEdit,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

defineProps<{
  dateRange: DateRange;
  rangeIdx: number;
  active: boolean;
  color: string;
  formatMapRange: (dr: DateRange) => string;
}>();

const emit = defineEmits<{
  click: [];
  delete: [];
  edit: [rangeIdx: number, range: DateRange];
}>();
</script>

<template>
  <div
    role="button"
    tabindex="0"
    :class="['nav-item', 'map-item', { visible: active }]"
    :style="{ '--country-color': color }"
    :aria-label="`${t('nav.map')}: ${formatMapRange(dateRange)}`"
    @click="$emit('click')"
    @keydown.enter="$emit('click')"
  >
    <div class="item-thumb map-thumb">
      <q-icon :name="symOutlinedMap" size="var(--type-md)" />
    </div>
    <div class="item-info">
      <span class="item-name">{{ t("nav.map") }}</span>
      <span class="map-dates">{{ formatMapRange(dateRange) }}</span>
    </div>
    <button
      type="button"
      class="map-action"
      :aria-label="t('nav.editMap')"
      @click.stop="emit('edit', rangeIdx, dateRange)"
    >
      <q-icon :name="symOutlinedEdit" size="var(--type-xs)" />
      <q-tooltip>{{ t("nav.editMap") }}</q-tooltip>
    </button>
    <button
      type="button"
      class="map-action"
      :aria-label="t('album.removeMap')"
      @click.stop="$emit('delete')"
    >
      <q-icon :name="symOutlinedClose" size="var(--type-xs)" />
      <q-tooltip>{{ t("album.removeMap") }}</q-tooltip>
    </button>
  </div>
</template>

<style lang="scss" scoped>
@use "nav-item";

.map-item .item-name {
  color: var(--q-primary);
}

.map-thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  color: var(--q-primary);
}

.map-dates {
  font-size: var(--type-xs);
  color: var(--text-muted);
}

.map-action {
  appearance: none;
  background: none;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
  padding: var(--gap-sm);
  border-radius: var(--radius-sm);
  color: var(--text-faint);
  opacity: 0;
  transition:
    opacity var(--duration-fast),
    color var(--duration-fast),
    background var(--duration-fast);

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

  &:focus-visible {
    opacity: 1;
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 1px;
  }
}

@media (hover: none) {
  .map-action {
    opacity: 1;
  }
}

@media (pointer: coarse) {
  .map-action {
    min-width: 2.75rem;
    min-height: 2.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--gap-md-lg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .map-action {
    transition: none;
  }
}
</style>
