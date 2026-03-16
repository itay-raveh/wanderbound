<script lang="ts" setup>
import type { Album, AlbumUpdate, Step } from "@/client";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { usePdfExportStream } from "@/composables/usePdfExportStream";
import { formatShortDate, isoDate, qDateNavBounds, toIso, toQDate } from "@/utils/date";
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
    .map(([from, to]) => `${formatShortDate(from)} → ${formatShortDate(to)}`)
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
  <div class="sidebar column no-wrap overflow-hidden">
    <div class="sidebar-scroll scroll q-py-xs">
      <!-- Trip selector -->
      <div class="section column no-wrap q-gutter-y-sm">
        <div class="section-label text-overline text-weight-semibold text-faint">Trip</div>
        <q-select
          v-model="albumId"
          :options="albumOptions"
          class="compact-field"
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
      </div>

      <q-separator class="q-mx-md" />

      <template v-if="album">
        <!-- Step range picker -->
        <div v-if="allSteps?.length" class="section column no-wrap q-gutter-y-sm">
          <div class="section-label text-overline text-weight-semibold text-faint">Steps</div>
          <q-input
            :model-value="rangeDisplay"
            class="compact-field"
            dense
            outlined
            readonly
            label="Date range"
            stack-label
          >
            <template #append>
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
        </div>

      </template>
    </div>

    <!-- Sticky export footer -->
    <div v-if="album" class="sidebar-footer">
      <q-btn
        color="primary"
        unelevated
        no-caps
        :loading="pdfBusy"
        class="full-width"
        @click="onExportPdf"
      >
        <q-icon :name="symOutlinedPictureAsPdf" size="1.25rem" />
        {{ pdf.buttonLabel.value }}
        <template #loading>
          <q-spinner-dots color="white" size="1.25rem" />
          {{ pdf.buttonLabel.value }}
        </template>
      </q-btn>
      <div v-if="pdfBusy" class="pdf-progress overflow-hidden">
        <div class="pdf-progress-bar" :style="{ width: `${pdf.progress.value * 100}%` }" />
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.sidebar {
  height: 100%;
}

.sidebar-scroll {
  flex: 1;
}

.section {
  padding: 0.75rem 1rem;
}

.sidebar-footer {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--border-color);
}

.pdf-progress {
  height: 3px;
  margin-top: 0.375rem;
  border-radius: var(--radius-xs);
  background: var(--border-color);
}

.pdf-progress-bar {
  height: 100%;
  background: var(--q-primary);
  border-radius: var(--radius-xs);
  transition: width var(--duration-normal) ease;
}
</style>
