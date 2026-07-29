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
    :class="['map-item', { visible: active }]"
    :style="{ '--country-color': color }"
  >
    <button
      type="button"
      :class="['nav-item', 'map-target', { visible: active }]"
      :aria-current="active ? 'page' : undefined"
      :aria-label="`${t('nav.map')}: ${formatMapRange(dateRange)}`"
      @click="$emit('click')"
    >
      <div class="item-thumb map-thumb">
        <q-icon :name="symOutlinedMap" size="var(--type-md)" />
      </div>
      <div class="item-info">
        <span class="item-name">{{ t("nav.map") }}</span>
        <span class="map-dates">{{ formatMapRange(dateRange) }}</span>
      </div>
    </button>
    <div class="map-actions">
      <button
        type="button"
        class="map-action"
        :aria-label="t('nav.editMap')"
        @click="emit('edit', rangeIdx, dateRange)"
      >
        <q-icon :name="symOutlinedEdit" size="var(--type-xs)" />
        <q-tooltip>{{ t("nav.editMap") }}</q-tooltip>
      </button>
      <button
        type="button"
        class="map-action"
        :aria-label="t('album.removeMap')"
        @click="$emit('delete')"
      >
        <q-icon :name="symOutlinedClose" size="var(--type-xs)" />
        <q-tooltip>{{ t("album.removeMap") }}</q-tooltip>
      </button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
@use "nav-item";
@use "nav-toggle";

.map-item {
  position: relative;
}

.map-target {
  padding-inline-end: 4.75rem;
}

.map-target .item-name {
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

.map-actions {
  position: absolute;
  inset-inline-end: var(--gap-sm);
  top: 50%;
  display: flex;
  opacity: 0;
  transform: translateY(-50%);
  transition: opacity var(--duration-fast);

  .map-item:hover &,
  .map-item.visible &,
  .map-item:focus-within & {
    opacity: 1;
  }
}

.map-action {
  @include nav-toggle.nav-toggle(1);
}

@media (hover: none) {
  .map-actions {
    opacity: 1;
  }
}

@media (pointer: coarse) {
  .map-target {
    padding-inline-end: 6.25rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .map-actions {
    transition: none;
  }
}
</style>
