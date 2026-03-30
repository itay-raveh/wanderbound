<script lang="ts" setup>
import type { Album, Step, Media } from "@/client";
import UnusedDrawer from "./UnusedDrawer.vue";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { mediaThumbUrl, isVideo } from "@/utils/media";
import { useI18n } from "vue-i18n";
import { computed } from "vue";
import { matImage, matMap, matBarChart } from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = defineProps<{
  album: Album;
  media: Media[];
  step?: Step;
  sectionKey?: string | null;
}>();

type Context = "step" | "cover" | "map" | "overview" | "empty";

const context = computed<Context>(() => {
  if (props.step) return "step";
  const key = props.sectionKey;
  if (!key) return "empty";
  if (key === "cover-front" || key === "cover-back") return "cover";
  if (key === "overview") return "overview";
  if (key === "full-map" || key.startsWith("map-") || key.startsWith("hike-")) return "map";
  return "empty";
});

// ── Cover photo selection ──────────────────────────────────────────────
const albumMutation = useAlbumMutation(() => props.album.id);
const isCoverBack = computed(() => props.sectionKey === "cover-back");
const coverField = computed(() =>
  isCoverBack.value ? "back_cover_photo" as const : "front_cover_photo" as const,
);
const activeCoverPhoto = computed(() => props.album[coverField.value]);

const landscapePhotos = computed(() =>
  props.media.filter((m) => m.width / m.height > 4 / 5 && !isVideo(m.name)).map((m) => m.name),
);

function selectCoverPhoto(name: string) {
  albumMutation.mutate({ [coverField.value]: name });
}

// ── Panel metadata ─────────────────────────────────────────────────────
const panelIcon = computed(() => {
  switch (context.value) {
    case "cover": return matImage;
    case "map": return matMap;
    case "overview": return matBarChart;
    default: return matImage;
  }
});

const panelLabel = computed(() => {
  switch (context.value) {
    case "cover":
      return isCoverBack.value ? t("album.backCover") : t("album.frontCover");
    case "map":
      if (props.sectionKey === "full-map") return t("album.tripRouteMap");
      if (props.sectionKey?.startsWith("hike-")) return t("hike.mapLabel");
      return t("nav.map");
    case "overview":
      return t("inspector.overview");
    default:
      return "";
  }
});
</script>

<template>
  <!-- Step: unused photos tray -->
  <UnusedDrawer v-if="context === 'step'" :step="step!" :album-id="album.id" />

  <!-- Non-step: contextual inspector -->
  <div v-else class="inspector-panel">
    <div
      v-if="context !== 'empty'"
      class="panel-header row no-wrap items-center text-overline text-weight-semibold text-muted"
    >
      <q-icon :name="panelIcon" size="var(--type-md)" />
      <span>{{ panelLabel }}</span>
    </div>

    <!-- Cover: photo picker grid -->
    <template v-if="context === 'cover'">
      <div v-if="landscapePhotos.length" class="cover-grid">
        <img
          v-for="photo in landscapePhotos"
          :key="photo"
          :src="mediaThumbUrl(photo, album.id)"
          class="cover-cell"
          :class="{ selected: photo === activeCoverPhoto }"
          :aria-label="t('album.selectPhoto')"
          role="button"
          tabindex="0"
          loading="lazy"
          alt=""
          @click="selectCoverPhoto(photo)"
          @keydown.enter="selectCoverPhoto(photo)"
          @keydown.space.prevent="selectCoverPhoto(photo)"
        >
      </div>
      <div v-else class="panel-hint">{{ t("album.noLandscapePhotos") }}</div>
    </template>

    <!-- Map / Hike: informational -->
    <div v-else-if="context === 'map'" class="panel-hint">
      {{ t("inspector.mapHint") }}
    </div>

    <!-- Overview: informational -->
    <div v-else-if="context === 'overview'" class="panel-hint">
      {{ t("inspector.overviewHint") }}
    </div>
  </div>
</template>

<style lang="scss" scoped>
.inspector-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  padding: var(--gap-md);
}

.panel-header {
  gap: var(--gap-sm);
  margin-bottom: var(--gap-md);
  flex-shrink: 0;
}

.panel-hint {
  font-size: var(--type-xs);
  color: var(--text-faint);
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
  aspect-ratio: 297 / 210;
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
