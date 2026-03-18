<script lang="ts" setup>
import type { Album, AlbumUpdate, Step } from "@/client";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useUserQuery } from "@/queries/useUserQuery";
import { usePdfExportStream } from "@/composables/usePdfExportStream";
import { isoDate, parseLocalDate, qDateNavBounds, toIso, toQDate } from "@/utils/date";
import {
  symOutlinedCalendarMonth,
  symOutlinedFlightTakeoff,
  symOutlinedPictureAsPdf,
} from "@quasar/extras/material-symbols-outlined";
import { computed } from "vue";

const props = defineProps<{
  albumIds: string[];
  album?: Album;
  allSteps?: Step[];
}>();

const albumId = defineModel<string | null>("albumId");

const albumMutation = useAlbumMutation(() => props.album?.id ?? "");
const { formatDateRange } = useUserQuery();
const pdf = usePdfExportStream(() => props.album?.id ?? "");
const pdfBusy = computed(() => pdf.state.value !== "idle" && pdf.state.value !== "error");

function save(patch: AlbumUpdate) {
  if (!props.album) return;
  albumMutation.mutate(patch);
}

const albumOptions = computed(() =>
  props.albumIds.map((value) => ({ label: toTitleCase(value), value })),
);

const toTitleCase = (str: string) =>
  str
    .replace(/([a-z])-/g, "$1 ")
    .replace(/_\d+$/, "")
    .replace(
      /\w\S*/g,
      (text) => text.charAt(0).toUpperCase() + text.substring(1).toLowerCase(),
    );

function onExportPdf() {
  if (!props.album) return;
  pdf.start();
}

// --- Step date picker (multiple date ranges) ---

type QDateRange = { from: string; to: string };

/** Set of QDate-format dates that have steps — for the `options` prop. */
const stepDates = computed(() => {
  const set = new Set<string>();
  for (const step of props.allSteps ?? []) {
    set.add(toQDate(isoDate(step.datetime)));
  }
  return set;
});

function isStepDate(date: string): boolean {
  return stepDates.value.has(date);
}

const nav = computed(() => qDateNavBounds(props.allSteps ?? []));

/** Album date ranges → QDate model. */
const dateRangeModel = computed(() => {
  const ranges = props.album?.steps_ranges;
  if (!ranges?.length) return undefined;
  return ranges.map(([from, to]) => ({ from: toQDate(from), to: toQDate(to) }));
});

const rangeDisplay = computed(() => {
  const ranges = props.album?.steps_ranges;
  if (!ranges?.length) return "";
  return ranges
    .map(([from, to]) =>
      formatDateRange(parseLocalDate(from), parseLocalDate(to), { day: "numeric", month: "short" }),
    )
    .join(", ");
});

function onRangePick(val: (QDateRange | string)[] | QDateRange | string | null) {
  if (!val) {
    save({ steps_ranges: [] });
    return;
  }
  const entries = Array.isArray(val) ? val : [val];
  const ranges: [string, string][] = entries.map((e) => {
    if (typeof e === "string") return [toIso(e), toIso(e)];
    const a = toIso(e.from), b = toIso(e.to);
    return a <= b ? [a, b] : [b, a];
  });
  save({ steps_ranges: ranges.sort(([a], [b]) => a.localeCompare(b)) });
}
</script>

<template>
  <div class="album-toolbar row no-wrap items-center q-gutter-x-sm">
    <!-- Trip selector -->
    <q-select
      v-model="albumId"
      :options="albumOptions"
      class="compact-field toolbar-field"
      dense
      outlined
      options-dense
      emit-value
      map-options
    >
      <template #prepend>
        <q-icon :name="symOutlinedFlightTakeoff" size="1.125rem" />
      </template>
    </q-select>

    <!-- Date range picker -->
    <q-input
      v-if="album && allSteps?.length"
      :model-value="rangeDisplay"
      dir="auto"
      class="compact-field toolbar-field"
      dense
      outlined
      readonly
    >
      <template #prepend>
        <q-icon :name="symOutlinedCalendarMonth" size="1rem" class="cursor-pointer">
          <q-popup-proxy transition-show="scale" transition-hide="scale">
            <q-date
              :model-value="dateRangeModel"
              range
              multiple
              minimal
              :options="isStepDate"
              :navigation-min-year-month="nav.min"
              :navigation-max-year-month="nav.max"
              @update:model-value="onRangePick"
            />
          </q-popup-proxy>
        </q-icon>
      </template>
    </q-input>

    <!-- PDF export -->
    <q-btn
      v-if="album"
      class="toolbar-field"
      color="primary"
      unelevated
      no-caps
      dense
      :disable="pdfBusy"
      @click="onExportPdf"
    >
      <q-icon :name="symOutlinedPictureAsPdf" size="1.25rem" class="q-mr-xs" />
      Export PDF
    </q-btn>
  </div>
</template>

<style lang="scss" scoped>
.toolbar-field {
  width: 18rem;
}

</style>
