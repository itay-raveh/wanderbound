<script lang="ts" setup>
import type { DateRange } from "@/client";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { isoDate, parseYMD, qDateNavBounds, toQDate, ymdToIso } from "@/utils/date";
import {
  symOutlinedCalendarMonth,
  symOutlinedClose,
} from "@quasar/extras/material-symbols-outlined";
import { computed, nextTick, useTemplateRef } from "vue";

type YMD = ReturnType<typeof parseYMD>;

const props = defineProps<{
  albumId: string;
  mapsRanges: DateRange[];
  rangeIdx: number;
  dateRange: DateRange;
  steps: { datetime: string }[];
}>();

const albumMutation = useAlbumMutation(() => props.albumId);

/** QDate-format dates of visible steps — for date picker `options` prop. */
const stepQDates = computed(() => {
  const set = new Set<string>();
  for (const s of props.steps) set.add(toQDate(isoDate(s.datetime)));
  return set;
});

const nav = computed(() => qDateNavBounds(props.steps));

function endDateOptions(qdate: string) {
  const qStart = toQDate(props.dateRange[0]);
  return qdate >= qStart && stepQDates.value.has(qdate);
}

function deleteMap() {
  const ranges = [...props.mapsRanges];
  ranges.splice(props.rangeIdx, 1);
  albumMutation.mutate({ maps_ranges: ranges });
}

// --- Date picker popup management ---

const dateRef = useTemplateRef<{ setEditingRange: (r: YMD) => void }>("dateRef");
const popupRef = useTemplateRef<{ hide: () => void }>("popupRef");

async function onPopupShow() {
  await nextTick();
  dateRef.value?.setEditingRange(parseYMD(props.dateRange[0]));
}

function onRangeEnd(range: { from: YMD; to: YMD }) {
  const ranges = [...props.mapsRanges] as DateRange[];
  if (ranges[props.rangeIdx]) {
    ranges[props.rangeIdx] = [props.dateRange[0], ymdToIso(range.to)];
    albumMutation.mutate({ maps_ranges: ranges });
  }
  popupRef.value?.hide();
}
</script>

<template>
  <div class="map-controls">
    <q-icon
      :name="symOutlinedClose"
      size="1.125rem"
      class="map-control-btn"
      @click="deleteMap"
    >
      <q-tooltip>Remove map</q-tooltip>
    </q-icon>
    <q-icon :name="symOutlinedCalendarMonth" size="1.125rem" class="map-control-btn">
      <q-tooltip>Change date range</q-tooltip>
      <q-popup-proxy
        ref="popupRef"
        transition-show="scale"
        transition-hide="scale"
        @before-show="onPopupShow"
      >
        <q-date
          ref="dateRef"
          :model-value="{ from: toQDate(dateRange[0]), to: toQDate(dateRange[1]) }"
          range
          minimal
          :options="endDateOptions"
          :navigation-min-year-month="nav.min"
          :navigation-max-year-month="nav.max"
          @range-end="onRangeEnd"
        />
      </q-popup-proxy>
    </q-icon>
  </div>
</template>

<style lang="scss" scoped>
.map-controls {
  position: absolute;
  top: 0.5rem;
  left: 0.5rem;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem;
  background: color-mix(in srgb, var(--surface) 85%, transparent);
  backdrop-filter: blur(8px);
  border-radius: 0.375rem;
  border: 1px solid var(--border-color);
  color: var(--text-muted);
}

.map-control-btn {
  cursor: pointer;
  padding: 0.25rem;
  border-radius: 0.25rem;
  transition: color 0.15s, background 0.15s;

  &:hover {
    color: var(--text);
    background: color-mix(in srgb, var(--text) 8%, transparent);
  }
}
</style>
