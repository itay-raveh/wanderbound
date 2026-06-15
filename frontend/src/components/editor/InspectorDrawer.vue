<script lang="ts" setup>
import type { AlbumMedia, AlbumMeta, StepRead as Step } from "@/client";
import AlbumProperties from "./AlbumProperties.vue";
import CoverCell from "./CoverCell.vue";
import MediaPanel from "./MediaPanel.vue";
import UnusedDrawer from "./UnusedDrawer.vue";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { provideAlbum } from "@/composables/useAlbum";
import {
  THUMB_WIDTHS,
  mediaThumbUrl,
  isVideo,
  isPortrait,
} from "@/utils/media";
import {
  DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
  type MediaResolutionWarningPreset,
} from "@/utils/photoQuality";
import { useUserQuery } from "@/queries/useUserQuery";
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";

const { t } = useI18n();

const props = defineProps<{
  album: AlbumMeta;
  media: AlbumMedia[];
  steps: Step[];
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

const landscapeMedia = computed(() =>
  props.media.filter((m) => !isPortrait(m) && !isVideo(m.name)),
);
const COVER_GRID_COLUMNS = 2;
const COVER_GRID_ROW_SIZE = 92;
const COVER_GRID_SLICE_ROWS = 8;

const landscapeRows = computed(() => {
  const rows: AlbumMedia[][] = [];
  for (let i = 0; i < landscapeMedia.value.length; i += COVER_GRID_COLUMNS) {
    rows.push(landscapeMedia.value.slice(i, i + COVER_GRID_COLUMNS));
  }
  return rows;
});

const propertiesOpen = ref(true);
const externalMediaOpen = ref(false);

function selectCoverPhoto(name: string) {
  albumMutation.mutate({ [coverField.value]: name });
}

function coverPhotoIndex(
  rowIndex: number | string,
  columnIndex: number | string,
): number {
  return Number(rowIndex) * COVER_GRID_COLUMNS + Number(columnIndex) + 1;
}

const resolutionWarningPreset = computed<MediaResolutionWarningPreset>(
  () =>
    props.album.media_resolution_warning_preset ??
    DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
);

function updateResolutionWarningPreset(value: MediaResolutionWarningPreset) {
  albumMutation.mutate({ media_resolution_warning_preset: value });
}

const panelLabel = computed(() =>
  isCoverBack.value ? t("album.backCover") : t("album.frontCover"),
);

const { countryName } = useUserQuery();

const importTargetLabel = computed<string | null>(() => {
  const s = props.step;
  if (!s) return null;
  const name = s.name?.trim();
  if (name) return name;
  const locName = s.location?.name?.trim();
  if (locName) return locName;
  const country = countryName(
    s.location?.country_code ?? "",
    s.location?.detail ?? "",
  );
  return country || t("externalMedia.import.unnamedStep");
});
</script>

<template>
  <div class="inspector-panel">
    <q-expansion-item
      v-model="propertiesOpen"
      group="inspector-primary"
      class="panel-section"
      header-class="panel-section-header"
      expand-icon-class="text-faint"
      :label="t('editor.properties')"
    >
      <AlbumProperties :album="album" :steps="steps" :media="media" />
    </q-expansion-item>

    <q-expansion-item
      v-model="externalMediaOpen"
      group="inspector-primary"
      class="panel-section"
      header-class="panel-section-header"
      expand-icon-class="text-faint"
      :label="t('externalMedia.section')"
    >
      <MediaPanel
        :album-id="album.id"
        :context="context"
        :step-id="step?.id"
        :target-label="importTargetLabel"
        :media="media"
        :resolution-warning-preset="resolutionWarningPreset"
        @update:resolution-warning-preset="updateResolutionWarningPreset"
      />
    </q-expansion-item>

    <div class="inspector-context-tray">
      <!-- Step: unused photos tray -->
      <div v-if="context === 'step'" class="context-section">
        <UnusedDrawer
          :key="step!.unused.join('|')"
          :step="step!"
          :album-id="album.id"
          class="unused-section"
        />
      </div>

      <!-- Cover: photo picker grid -->
      <div v-else-if="context === 'cover'" class="context-section">
        <div
          class="context-tray-header row no-wrap items-center text-overline text-weight-semibold text-muted"
        >
          <span>{{ panelLabel }}</span>
          <span class="text-faint">{{ landscapeMedia.length }}</span>
        </div>
        <q-virtual-scroll
          v-if="landscapeMedia.length"
          class="cover-grid"
          :items="landscapeRows"
          :virtual-scroll-item-size="COVER_GRID_ROW_SIZE"
          :virtual-scroll-slice-size="COVER_GRID_SLICE_ROWS"
        >
          <template #default="{ item: row, index: rowIndex }">
            <div class="cover-row">
              <CoverCell
                v-for="(media, columnIndex) in row"
                :key="media.name"
                :src="
                  mediaThumbUrl(
                    media.name,
                    album.id,
                    THUMB_WIDTHS[0],
                    media.updated_at,
                  )
                "
                :selected="media.name === activeCoverPhoto"
                :label="
                  t('album.selectCoverPhoto', {
                    index: coverPhotoIndex(rowIndex, columnIndex),
                    total: landscapeMedia.length,
                  })
                "
                @select="selectCoverPhoto(media.name)"
              />
            </div>
          </template>
        </q-virtual-scroll>
        <div v-else class="panel-hint">{{ t("album.noLandscapePhotos") }}</div>
      </div>

      <div v-else class="context-section context-section-empty" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.inspector-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  background: var(--bg-secondary);
}

.panel-section {
  border-top: 1px solid var(--border-color);
}

.inspector-context-tray {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border-color);
}

.context-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: var(--gap-md);
}

.context-section-empty {
  padding: 0;
}

.unused-section {
  flex: 1;
  min-height: 0;
}

.context-tray-header {
  gap: var(--gap-xs);
  min-height: 2rem;
  padding-block-end: var(--gap-sm);
  letter-spacing: var(--tracking-wide);
}

.panel-hint {
  font-size: var(--type-xs);
  color: var(--text-muted);
  line-height: 1.5;
}

:deep(.panel-section-header) {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  font-size: var(--type-xs);
  font-weight: 700;
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
  color: var(--text-muted);
}

// ── Cover photo grid ──

.cover-grid {
  flex: 1;
  overflow-y: auto;
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

.cover-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--gap-sm);
  padding-block-end: var(--gap-sm);
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
</style>
