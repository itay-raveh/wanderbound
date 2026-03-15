<script lang="ts" setup>
import type { Album, AlbumUpdate } from "@/client";
import { toRangeList } from "@/utils/ranges";
import { chooseTextDir } from "@/utils/text";
import { isVideo } from "@/utils/media";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { usePdfExportStream } from "@/composables/usePdfExportStream";
import CoverPhotoPicker from "./CoverPhotoPicker.vue";
import { symOutlinedFlightTakeoff, symOutlinedPictureAsPdf } from "@quasar/extras/material-symbols-outlined";
import { computed } from "vue";

const props = defineProps<{
  albumIds: string[];
  album?: Album;
}>();

const albumId = defineModel<string | null>("albumId");

const albumMutation = useAlbumMutation(() => props.album?.id ?? "");
const pdf = usePdfExportStream(() => props.album?.id ?? "");
const pdfBusy = computed(() => pdf.state.value !== "idle" && pdf.state.value !== "error");

function save(patch: AlbumUpdate) {
  if (!props.album) return;
  albumMutation.mutate(patch);
}

const onTripSelected = (aid: string) => {
  albumId.value = aid;
};

const ruleRequired = (val: string): true | string => {
  if (!val || !val.trim()) return "Step ranges are required";
  return true;
};
const ruleRangesFormat = (val: string): true | string => {
  try {
    toRangeList(val);
  } catch {
    return "Use format: 0-20 or 0-5, 10-15";
  }
  return true;
};

const toTitleCase = (str: string) =>
  str
    .replace(/([a-z])-/g, "$1 ")
    .replace(/_\d+$/, "")
    .replace(
      /\w\S*/g,
      (text) => text.charAt(0).toUpperCase() + text.substring(1).toLowerCase(),
    );

const landscapePhotos = computed(() => {
  const orientations = (props.album?.orientations ?? {}) as Record<string, string>;
  return Object.keys(orientations).filter(
    (name) => orientations[name] === "l" && !isVideo(name),
  );
});

function onExportPdf() {
  if (!props.album) return;
  pdf.start();
}
</script>

<template>
  <div class="sidebar">
    <div class="sidebar-scroll">
      <!-- Trip selector -->
      <div class="section">
        <div class="section-label">Trip</div>
        <q-select
          :model-value="albumId"
          :options="albumIds.map((value) => ({ label: toTitleCase(value), value }))"
          class="sidebar-field"
          dense
          outlined
          options-dense
          emit-value
          map-options
          @update:model-value="onTripSelected"
        >
          <template #prepend>
            <q-icon :name="symOutlinedFlightTakeoff" size="1.125rem" class="field-icon" />
          </template>
        </q-select>
      </div>

      <div class="divider" />

      <template v-if="album">
        <!-- Album details -->
        <div class="section">
          <div class="section-label">Details</div>
          <q-input
            :model-value="album.title"
            :dir="chooseTextDir(album.title)"
            class="sidebar-field"
            dense
            outlined
            label="Title"
            @update:model-value="save({ title: String($event) })"
          />
          <q-input
            :model-value="album.subtitle"
            :dir="chooseTextDir(album.subtitle)"
            class="sidebar-field"
            dense
            outlined
            label="Subtitle"
            @update:model-value="save({ subtitle: String($event) })"
          />
        </div>

        <div class="divider" />

        <!-- Cover photos -->
        <div class="section">
          <div class="section-label">Covers</div>
          <CoverPhotoPicker
            :model-value="album.front_cover_photo"
            :album-id="album.id"
            :photos="landscapePhotos"
            label="Front Cover"
            @update:model-value="save({ front_cover_photo: $event })"
          />
          <CoverPhotoPicker
            :model-value="album.back_cover_photo"
            :album-id="album.id"
            :photos="landscapePhotos"
            label="Back Cover"
            @update:model-value="save({ back_cover_photo: $event })"
          />
        </div>

        <div class="divider" />

        <!-- Ranges -->
        <div class="section">
          <div class="section-label">Ranges</div>
          <q-input
            :model-value="album.steps_ranges"
            :rules="[ruleRequired, ruleRangesFormat]"
            class="sidebar-field"
            debounce="500"
            dense
            outlined
            lazy-rules
            label="Steps"
            stack-label
            placeholder="e.g. 0-20, 30"
            @update:model-value="save({ steps_ranges: String($event) })"
          />
          <q-input
            :model-value="album.maps_ranges"
            :rules="[ruleRangesFormat]"
            class="sidebar-field"
            debounce="500"
            dense
            outlined
            lazy-rules
            label="Maps"
            stack-label
            placeholder="e.g. 0-20, 30"
            @update:model-value="save({ maps_ranges: String($event) })"
          />
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
