<script lang="ts" setup>
import type { AlbumMedia, AlbumMeta, StepRead as Step } from "@/client";
import AlbumProperties from "./AlbumProperties.vue";
import CoverCell from "./CoverCell.vue";
import MediaPanel from "./MediaPanel.vue";
import UnusedDrawer from "./UnusedDrawer.vue";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { provideAlbum } from "@/composables/useAlbum";
import { THUMB_WIDTHS, mediaThumbUrl, isVideo, isPortrait } from "@/utils/media";
import { DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET } from "@/utils/photoQuality";
import { useI18n } from "vue-i18n";
import { computed, ref, watch } from "vue";
import { matImage } from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = defineProps<{
  album: AlbumMeta;
  media: AlbumMedia[];
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

const coverGridRef = ref<HTMLElement | null>(null);
const externalMediaOpen = ref(true);
const unusedOpen = ref(true);
const coverOpen = ref(true);

watch(
  context,
  (next, prev) => {
    if (next === prev) return;
    if (next === "step") unusedOpen.value = true;
    if (next === "cover") coverOpen.value = true;
  },
  { immediate: true },
);

function selectCoverPhoto(name: string) {
  albumMutation.mutate({ [coverField.value]: name });
}

// ── Panel metadata ─────────────────────────────────────────────────────
const panelIcon = matImage;
const panelLabel = computed(() =>
  isCoverBack.value ? t("album.backCover") : t("album.frontCover"),
);
</script>

<template>
  <div class="inspector-panel">
    <AlbumProperties :album="album" />
    <q-separator class="properties-separator" />

    <q-expansion-item
      v-model="externalMediaOpen"
      class="panel-section"
      header-class="panel-section-header"
      expand-icon-class="text-faint"
      :label="t('externalMedia.section')"
    >
      <MediaPanel :album-id="album.id" :context="context" :step-id="step?.id" />
    </q-expansion-item>

    <!-- Step: unused photos tray -->
    <q-expansion-item
      v-if="context === 'step'"
      v-model="unusedOpen"
      class="panel-section"
      header-class="panel-section-header"
      expand-icon-class="text-faint"
      label="Unused"
    >
      <div class="context-section">
        <UnusedDrawer
          :key="step!.unused.join('|')"
          :step="step!"
          :album-id="album.id"
          class="unused-section"
        />
      </div>
    </q-expansion-item>

    <!-- Cover: photo picker grid -->
    <q-expansion-item
      v-else-if="context === 'cover'"
      v-model="coverOpen"
      class="panel-section"
      header-class="panel-section-header"
      expand-icon-class="text-faint"
      :label="panelLabel"
    >
      <div class="context-section">
        <div
          class="panel-header row no-wrap items-center text-overline text-weight-semibold text-muted"
        >
          <q-icon :name="panelIcon" size="var(--type-md)" />
          <span>{{ panelLabel }}</span>
        </div>
        <div
          v-if="landscapeMedia.length"
          ref="coverGridRef"
          class="cover-grid"
        >
          <CoverCell
            v-for="(media, index) in landscapeMedia"
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
            :lazy-root="coverGridRef"
            :label="
              t('album.selectCoverPhoto', {
                index: index + 1,
                total: landscapeMedia.length,
              })
            "
            @select="selectCoverPhoto(media.name)"
          />
        </div>
        <div v-else class="panel-hint">{{ t("album.noLandscapePhotos") }}</div>
      </div>
    </q-expansion-item>
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

.properties-separator {
  flex-shrink: 0;
  margin-inline: var(--gap-md);
}

.panel-section {
  border-top: 1px solid var(--border-color);
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
</style>
