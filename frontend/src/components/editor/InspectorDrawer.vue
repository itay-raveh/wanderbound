<script lang="ts" setup>
import type { Album, Step, Media } from "@/client";
import AlbumProperties from "./AlbumProperties.vue";
import CoverCell from "./CoverCell.vue";
import UnusedDrawer from "./UnusedDrawer.vue";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { provideAlbum } from "@/composables/useAlbum";
import { useMediaImport } from "@/composables/useMediaImport";
import { mediaThumbUrl, isVideo, isPortrait } from "@/utils/media";
import { DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET } from "@/utils/photoQuality";
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";
import {
  matAddPhotoAlternate,
  matComputer,
  matImage,
  matPhotoLibrary,
} from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = defineProps<{
  album: Album;
  media: Media[];
  step?: Step;
  sectionKey?: string | null;
}>();

// Provide album context so child components (MediaItem in UnusedDrawer)
// can call useAlbum() even though InspectorDrawer lives outside AlbumViewer.
provideAlbum({
  albumId: computed(() => props.album.id),
  colors: computed(() => (props.album.colors ?? {}) as Record<string, string>),
  media: computed(() => props.media),
  tripStart: computed(() => ""),
  totalDays: computed(() => 1),
  mediaResolutionWarningPreset: computed(
    () =>
      props.album.media_resolution_warning_preset ??
      DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
  ),
});

type Context = "step" | "cover" | "map" | "overview" | "empty";

const context = computed<Context>(() => {
  if (props.step) return "step";
  const key = props.sectionKey;
  if (!key) return "empty";
  if (key === "cover-front" || key === "cover-back") return "cover";
  if (key === "overview") return "overview";
  if (key === "full-map" || key.startsWith("map-") || key.startsWith("hike-"))
    return "map";
  return "empty";
});

// ── Cover photo selection ──────────────────────────────────────────────
const albumMutation = useAlbumMutation(() => props.album.id);
const isCoverBack = computed(() => props.sectionKey === "cover-back");
const coverField = computed(() =>
  isCoverBack.value
    ? ("back_cover_photo" as const)
    : ("front_cover_photo" as const),
);
const activeCoverPhoto = computed(() => props.album[coverField.value]);

const landscapePhotos = computed(() =>
  props.media
    .filter((m) => !isPortrait(m) && !isVideo(m.name))
    .map((m) => m.name),
);

const coverGridRef = ref<HTMLElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const pendingDeviceTarget = ref<{ context: "step" | "cover"; stepId?: number } | null>(
  null,
);
const mediaImport = useMediaImport(() => props.album.id);

function selectCoverPhoto(name: string) {
  albumMutation.mutate({ [coverField.value]: name });
}

const canImportMedia = computed(() => context.value === "step" || context.value === "cover");
const importTarget = computed(() => {
  if (context.value === "step" && props.step) {
    return { context: "step" as const, stepId: props.step.id };
  }
  if (context.value === "cover") return { context: "cover" as const };
  return null;
});

function pickDeviceFiles() {
  const target = importTarget.value;
  if (!target) return;
  pendingDeviceTarget.value = target;
  fileInputRef.value?.click();
}

function onDeviceFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = input.files;
  const target = pendingDeviceTarget.value;
  input.value = "";
  pendingDeviceTarget.value = null;
  if (!files?.length || !target) return;
  void mediaImport.importDevice(files, target);
}

function importFromGoogle() {
  const target = importTarget.value;
  if (!target || mediaImport.googlePhotosState.value === "unavailable") return;
  void mediaImport.importGoogle(target);
}

// ── Panel metadata ─────────────────────────────────────────────────────
const panelIcon = matImage;
const panelLabel = computed(() =>
  isCoverBack.value ? t("album.backCover") : t("album.frontCover"),
);

const importProgressFraction = computed(() => {
  const { done, total } = mediaImport.progress.value;
  return total > 0 ? done / total : 0;
});

const importDialogTitle = computed(() => {
  switch (mediaImport.phase.value) {
    case "authorizing":
      return t("mediaImport.authorizing");
    case "picking":
      return t("mediaImport.picking");
    case "uploading":
      return t("mediaImport.uploading");
    case "processing":
      return t("mediaImport.processing");
    case "done":
      return t(
        "mediaImport.done",
        { count: mediaImport.importedCount.value },
        mediaImport.importedCount.value,
      );
    case "error":
      return mediaImport.errorDetail.value ?? t("mediaImport.error");
    default:
      return "";
  }
});
</script>

<template>
  <div class="inspector-panel">
    <AlbumProperties :album="album" />
    <q-separator class="properties-separator" />
    <input
      ref="fileInputRef"
      type="file"
      class="hidden-input"
      accept="image/*,video/*"
      multiple
      @change="onDeviceFilesSelected"
    />

    <div v-if="canImportMedia" class="import-bar">
      <q-btn
        dense
        no-caps
        unelevated
        color="primary"
        class="import-btn"
        :disable="mediaImport.isBusy.value"
        :icon="matAddPhotoAlternate"
        :label="t('mediaImport.addMedia')"
      >
        <q-menu anchor="bottom start" self="top start">
          <q-list dense class="import-menu">
            <q-item v-close-popup clickable @click="pickDeviceFiles">
              <q-item-section avatar>
                <q-icon :name="matComputer" />
              </q-item-section>
              <q-item-section>{{ t("mediaImport.device") }}</q-item-section>
            </q-item>
            <q-item
              v-close-popup
              clickable
              :disable="mediaImport.googlePhotosState.value === 'unavailable'"
              @click="importFromGoogle"
            >
              <q-item-section avatar>
                <q-icon :name="matPhotoLibrary" />
              </q-item-section>
              <q-item-section>{{ t("mediaImport.googlePhotos") }}</q-item-section>
            </q-item>
          </q-list>
        </q-menu>
      </q-btn>
    </div>

    <!-- Step: unused photos tray -->
    <div v-if="context === 'step'" class="context-section">
      <UnusedDrawer :step="step!" :album-id="album.id" class="unused-section" />
    </div>

    <!-- Cover: photo picker grid -->
    <div v-else-if="context === 'cover'" class="context-section">
      <div
        class="panel-header row no-wrap items-center text-overline text-weight-semibold text-muted"
      >
        <q-icon :name="panelIcon" size="var(--type-md)" />
        <span>{{ panelLabel }}</span>
      </div>
      <div v-if="landscapePhotos.length" ref="coverGridRef" class="cover-grid">
        <CoverCell
          v-for="(photo, index) in landscapePhotos"
          :key="photo"
          :src="mediaThumbUrl(photo, album.id)"
          :selected="photo === activeCoverPhoto"
          :lazy-root="coverGridRef"
          :label="
            t('album.selectCoverPhoto', {
              index: index + 1,
              total: landscapePhotos.length,
            })
          "
          @select="selectCoverPhoto(photo)"
        />
      </div>
      <div v-else class="panel-hint">{{ t("album.noLandscapePhotos") }}</div>
    </div>

    <q-dialog
      :model-value="mediaImport.phase.value !== 'idle'"
      persistent
      @hide="mediaImport.cancel"
    >
      <q-card class="import-dialog">
        <q-card-section class="row no-wrap items-center dialog-header">
          <q-icon :name="matAddPhotoAlternate" size="1.5rem" />
          <div class="text-subtitle1 text-weight-semibold">
            {{ importDialogTitle }}
          </div>
        </q-card-section>
        <q-card-section v-if="mediaImport.isBusy.value">
          <q-linear-progress
            :value="importProgressFraction"
            :indeterminate="importProgressFraction === 0"
            color="primary"
            rounded
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-if="mediaImport.isBusy.value"
            flat
            no-caps
            :label="t('common.cancel')"
            @click="mediaImport.cancel"
          />
          <q-btn
            v-else-if="mediaImport.phase.value === 'error'"
            flat
            no-caps
            color="primary"
            :label="t('common.close')"
            @click="mediaImport.cancel"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<style lang="scss" scoped>
.inspector-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
}

.properties-separator {
  flex-shrink: 0;
  margin-inline: var(--gap-md);
}

.hidden-input {
  position: absolute;
  width: 0.0625rem;
  height: 0.0625rem;
  opacity: 0;
  pointer-events: none;
}

.import-bar {
  padding: var(--gap-md) var(--gap-md) 0;
}

.import-btn {
  width: 100%;
  border-radius: var(--radius-sm);
}

.import-menu {
  min-width: 13rem;
}

.context-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: var(--gap-md);
}

.unused-section {
  flex: 1;
  min-height: 0;
}

.panel-header {
  gap: var(--gap-sm);
  margin-bottom: var(--gap-md);
  flex-shrink: 0;
}

.panel-hint {
  font-size: var(--type-xs);
  color: var(--text-muted);
  line-height: 1.5;
}

// ── Cover photo grid ──

.cover-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--gap-sm);
  overflow-y: auto;
  align-content: start;
  scrollbar-width: thin;
  scrollbar-color: var(--border-color) transparent;

  &::-webkit-scrollbar {
    width: 0.25rem;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: var(--radius-xs);
  }
}

.cover-cell {
  width: 100%;
  aspect-ratio: var(--page-aspect);
  object-fit: cover;
  cursor: pointer;
  border-radius: var(--radius-xs);
  outline: 0.125rem solid transparent;
  outline-offset: -0.125rem;
  transition: outline-color var(--duration-fast) ease;

  &.selected {
    outline-color: var(--q-primary);
  }

  &:hover:not(.selected) {
    outline-color: color-mix(in srgb, var(--text) 40%, transparent);
  }

  &:focus-visible {
    outline-color: var(--q-primary);
  }
}

@media (prefers-reduced-motion: reduce) {
  .cover-cell {
    transition: none;
  }
}

.dialog-header {
  gap: var(--gap-sm);
}

.import-dialog {
  width: min(24rem, 90vw);
  border-radius: var(--radius-sm);
}
</style>
