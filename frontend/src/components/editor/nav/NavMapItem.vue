<script lang="ts" setup>
import type { DateRange, Step } from "@/client";
import { toQDate, parseYMD, ymdToIso } from "@/utils/date";
import { makeRefCache } from "@/utils/refCache";
import StepDatePicker from "@/components/editor/StepDatePicker.vue";
import { useI18n } from "vue-i18n";
import { nextTick } from "vue";
import {
  symOutlinedMap,
  symOutlinedClose,
  symOutlinedCalendarMonth,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();

type YMD = ReturnType<typeof parseYMD>;
type DatePickerExpose = { setEditingRange: (r: YMD) => void };
type PopupExpose = { hide: () => void };

const props = defineProps<{
  dateRange: DateRange;
  rangeIdx: number;
  entryKey: string;
  active: boolean;
  steps: Step[];
  colors: Record<string, string>;
  formatMapRange: (dr: DateRange) => string;
}>();

const emit = defineEmits<{
  click: [];
  delete: [];
  dateChange: [rangeIdx: number, range: DateRange];
}>();

const { refs: datePickerRefs, setter: setDatePickerRef } = makeRefCache<DatePickerExpose>();
const { refs: popupProxyRefs, setter: setPopupRef } = makeRefCache<PopupExpose>();

function endDateOptions(dr: DateRange) {
  const min = toQDate(dr[0]);
  return (qdate: string) => qdate >= min;
}

async function onDateShow() {
  await nextTick();
  datePickerRefs.get(props.entryKey)?.setEditingRange(parseYMD(props.dateRange[0]));
}

function onDateEnd(range: { from: YMD; to: YMD }) {
  emit("dateChange", props.rangeIdx, [props.dateRange[0], ymdToIso(range.to)]);
  popupProxyRefs.get(props.entryKey)?.hide();
}
</script>

<template>
  <div
    role="button"
    tabindex="0"
    :class="['nav-item', 'map-item', { visible: active }]"
    :aria-label="`${t('nav.map')}: ${formatMapRange(dateRange)}`"
    @click="$emit('click')"
    @keydown.enter="$emit('click')"
  >
    <div class="item-thumb map-thumb">
      <q-icon :name="symOutlinedMap" size="var(--type-md)" />
    </div>
    <div class="item-info">
      <span class="item-name">{{ t("nav.map") }}</span>
      <button type="button" class="map-dates" aria-haspopup="dialog" @click.stop>
        <q-icon :name="symOutlinedCalendarMonth" size="var(--type-xs)" />
        {{ formatMapRange(dateRange) }}
        <q-popup-proxy
          :ref="setPopupRef(entryKey)"
          transition-show="scale"
          transition-hide="scale"
          @before-show="onDateShow"
        >
          <StepDatePicker
            :ref="setDatePickerRef(entryKey)"
            :model-value="{ from: toQDate(dateRange[0]), to: toQDate(dateRange[1]) }"
            :steps="steps"
            :colors="colors"
            range
            :options="endDateOptions(dateRange)"
            @range-end="(range: { from: YMD; to: YMD }) => onDateEnd(range)"
          />
        </q-popup-proxy>
      </button>
    </div>
    <button
      type="button"
      class="map-delete"
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

.item-thumb {
  width: 2.25rem;
  height: 1.75rem;
  flex-shrink: 0;
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.map-thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--q-primary) 12%, transparent);
  color: var(--q-primary);
}

.item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs);
}

.item-name {
  font-size: var(--type-xs);
  font-weight: 600;
  color: var(--text-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.map-dates {
  appearance: none;
  background: none;
  border: none;
  font: inherit;
  display: inline-flex;
  align-items: center;
  gap: var(--gap-xs);
  font-size: var(--type-xs);
  color: var(--text-muted);
  cursor: pointer;
  padding: var(--gap-xs);
  border-radius: var(--radius-xs);
  border-bottom: 0.0625rem dashed color-mix(in srgb, var(--text-muted) 50%, transparent);
  transition: background var(--duration-fast), color var(--duration-fast), border-color var(--duration-fast);

  &:hover {
    color: var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
    border-bottom-color: var(--q-primary);
    border-bottom-style: solid;
  }

  &:active {
    background: color-mix(in srgb, var(--q-primary) 16%, transparent);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

.map-delete {
  appearance: none;
  background: none;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
  padding: var(--gap-sm);
  border-radius: var(--radius-sm);
  color: var(--text-faint);
  opacity: 0;
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

  &:focus-visible {
    opacity: 1;
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.0625rem;
  }
}

@media (hover: none) {
  .map-delete {
    opacity: 1;
  }
}

@media (pointer: coarse) {
  .map-dates {
    padding: var(--gap-sm-md) var(--gap-md);
  }

  .map-delete {
    min-width: 2.75rem;
    min-height: 2.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--gap-md-lg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .map-dates,
  .map-delete {
    transition: none;
  }
}
</style>
