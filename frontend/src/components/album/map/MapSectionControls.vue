<script lang="ts" setup>
import type { DateRange, Step } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { parseYMD, toQDate, ymdToIso } from "@/utils/date";
import StepDatePicker from "@/components/editor/StepDatePicker.vue";
import {
  symOutlinedCalendarMonth,
  symOutlinedClose,
} from "@quasar/extras/material-symbols-outlined";
import { nextTick, useTemplateRef } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

type YMD = ReturnType<typeof parseYMD>;

const props = defineProps<{
  albumId: string;
  mapsRanges: DateRange[];
  rangeIdx: number;
  dateRange: DateRange;
  steps: Step[];
}>();

const { colors } = useAlbum();
const albumMutation = useAlbumMutation(() => props.albumId);

function endDateOptions(qdate: string) {
  return qdate >= toQDate(props.dateRange[0]);
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
  <div class="map-controls row no-wrap items-center text-muted">
    <q-icon
      :name="symOutlinedClose"
      size="1.125rem"
      class="map-control-btn cursor-pointer"
      @click="deleteMap"
    >
      <q-tooltip>{{ t("album.removeMap") }}</q-tooltip>
    </q-icon>
    <q-icon :name="symOutlinedCalendarMonth" size="1.125rem" class="map-control-btn cursor-pointer">
      <q-tooltip>{{ t("album.changeDateRange") }}</q-tooltip>
      <q-popup-proxy
        ref="popupRef"
        transition-show="scale"
        transition-hide="scale"
        @before-show="onPopupShow"
      >
        <StepDatePicker
          ref="dateRef"
          :model-value="{ from: toQDate(dateRange[0]), to: toQDate(dateRange[1]) }"
          :steps="steps"
          :colors="colors"
          range
          :options="endDateOptions"
          @range-end="onRangeEnd"
        />
      </q-popup-proxy>
    </q-icon>
  </div>
</template>

<style lang="scss" scoped>
.map-controls {
  position: absolute;
  top: var(--gap-md);
  /* rtl:ignore */
  left: var(--gap-md);
  z-index: 2;
  gap: var(--gap-sm);
  padding: var(--gap-sm);
  background: color-mix(in srgb, var(--surface) 85%, transparent);
  backdrop-filter: blur(8px);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.map-control-btn {
  padding: var(--gap-sm);
  border-radius: var(--radius-xs);
  transition: color var(--duration-fast), background var(--duration-fast);

  &:hover {
    color: var(--text);
    background: color-mix(in srgb, var(--text) 8%, transparent);
  }
}
</style>
