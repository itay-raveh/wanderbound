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
  <div class="sidebar">
    <div class="sidebar-scroll">
      <!-- Trip selector -->
      <div class="section">
        <div class="section-label">Trip</div>
        <q-select
          v-model="albumId"
          :options="albumOptions"
          class="sidebar-field"
          dense
          outlined
          options-dense
          emit-value
          map-options
        >
          <template #prepend>
            <q-icon :name="symOutlinedFlightTakeoff" size="1.125rem" class="field-icon" />
          </template>
        </q-select>
      </div>

      <div class="divider" />

      <template v-if="album">
        <!-- Step range picker -->
        <div v-if="allSteps?.length" class="section">
          <div class="section-label">Steps</div>
          <q-input
            :model-value="rangeDisplay"
            class="sidebar-field"
            dense
            outlined
            readonly
            label="Date range"
            stack-label
          >
            <template #append>
              <q-icon :name="symOutlinedCalendarMonth" size="1rem" class="cursor-pointer field-icon">
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
      <button
        class="export-btn"
        :disabled="pdfBusy"
        @click="onExportPdf"
      >
        <q-spinner-dots v-if="pdfBusy" size="1.25rem" color="white" />
        <q-icon v-else :name="symOutlinedPictureAsPdf" size="1.25rem" />
        <span>{{ pdf.buttonLabel.value }}</span>
      </button>
      <div v-if="pdfBusy" class="pdf-progress">
        <div class="pdf-progress-bar" :style="{ width: `${pdf.progress.value * 100}%` }" />
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.sidebar-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 0.25rem 0;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
}

.section-label {
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.divider {
  height: 1px;
  background: var(--border-color);
  margin: 0 1rem;
}

/* Quasar field overrides */

.sidebar-field {
  min-width: 0;

  &:deep(.q-field__control) {
    border-radius: 0.375rem;

    &::before {
      border-color: var(--border-color);
      transition: border-color 0.15s ease;
    }
  }

  &:deep(.q-field__control:hover)::before {
    border-color: var(--text-faint);
  }

  // Focus state
  &:deep(.q-field--focused .q-field__control)::after {
    border-color: var(--q-primary);
    border-width: 1px;
  }

  // Error state
  &:deep(.q-field--error .q-field__control)::before {
    border-color: var(--danger) !important;
  }

  &:deep(.q-field__native),
  &:deep(.q-field__input) {
    font-size: 0.8125rem;
    color: var(--text);
    text-overflow: ellipsis;
    overflow: hidden;
    white-space: nowrap;
  }

  &:deep(.q-field__label) {
    font-size: 0.8125rem;
    color: var(--text-muted);
  }

  &:deep(.q-field__native)::placeholder,
  &:deep(.q-field__input)::placeholder {
    color: var(--text-faint);
  }

  &:deep(.q-field__bottom) {
    padding: 0.1875rem 0.75rem 0;
    min-height: unset;
  }

  &:deep(.q-field__messages) {
    font-size: 0.6875rem;
    line-height: 1.3;
  }

  // Select-specific
  &:deep(.q-field__native > span) {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-bright);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.field-icon {
  color: var(--text-faint);
}

.sidebar-footer {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--border-color);
}

.export-btn {
  all: unset;
  cursor: pointer;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  height: 2.5rem;
  border-radius: 0.5rem;
  background: var(--q-primary);
  color: white;
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.01em;
  transition:
    opacity 0.15s ease,
    transform 0.1s ease;

  &:hover:not(:disabled) {
    opacity: 0.92;
  }

  &:active:not(:disabled) {
    transform: scale(0.985);
  }

  &:disabled {
    opacity: 0.65;
    cursor: not-allowed;
  }
}

.pdf-progress {
  height: 3px;
  margin-top: 0.375rem;
  border-radius: 2px;
  background: var(--border-color);
  overflow: hidden;
}

.pdf-progress-bar {
  height: 100%;
  background: var(--q-primary);
  border-radius: 2px;
  transition: width 0.3s ease;
}
</style>
