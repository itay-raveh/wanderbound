<script lang="ts" setup>
import { parseLocalDate } from "@/utils/date";
import { isVideo } from "@/utils/media";
import type { Album, Step } from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useI18n } from "vue-i18n";
import EditableText from "./EditableText.vue";
import CoverPhotoPicker from "./CoverPhotoPicker.vue";
import MediaItem from "./MediaItem.vue";
import { computed } from "vue";

const { formatDateRange } = useUserQuery();
const { t } = useI18n();

const props = defineProps<{
  album: Album;
  steps: Step[];
  isBack?: boolean;
}>();

const albumMutation = useAlbumMutation(() => props.album.id);

const coverMedia = computed(() =>
  props.isBack ? props.album.back_cover_photo : props.album.front_cover_photo,
);

const dates = computed(() => {
  const start = parseLocalDate(props.steps[0]!.datetime);
  const end = parseLocalDate(props.steps[props.steps.length - 1]!.datetime);
  return formatDateRange(start, end, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
});

const coverField = computed(() =>
  props.isBack ? "back_cover_photo" : "front_cover_photo",
);

const landscapePhotos = computed(() => {
  const mediaMap = (props.album.media ?? {}) as Record<string, string>;
  return Object.keys(mediaMap).filter(
    (name) => mediaMap[name] === "l" && !isVideo(name),
  );
});

function saveText(field: "title" | "subtitle", value: string) {
  albumMutation.mutate({ [field]: value });
}

function saveCover(name: string) {
  albumMutation.mutate({ [coverField.value]: name });
}
</script>

<template>
  <div class="page-container cover-page relative-position">
    <!-- Background photo (full bleed, no uniform dimming) -->
    <MediaItem
      v-if="coverMedia"
      :media="coverMedia"
      fit-cover
      :class="['fit', { 'cover-dimmed': !isBack }]"
    />

    <!-- Cover photo picker (editor only) -->
    <div class="cover-picker-anchor print-hide">
      <CoverPhotoPicker
        :model-value="coverMedia"
        :album-id="album.id"
        :photos="landscapePhotos"
        :label="isBack ? t('album.backCover') : t('album.frontCover')"
        @update:model-value="saveCover"
      />
    </div>

    <!-- ═══ FRONT COVER ═══ -->
    <template v-if="!isBack">
      <div class="front-text absolute-full">
        <div dir="auto" class="front-date">{{ dates }}</div>
        <div class="cover-rule" />

        <EditableText
          :model-value="album.title"
          dir="auto"
          class="front-title"
          @update:model-value="saveText('title', $event)"
        />

        <EditableText
          :model-value="album.subtitle"
          dir="auto"
          class="front-subtitle"
          @update:model-value="saveText('subtitle', $event)"
        />
      </div>
    </template>

    <!-- ═══ BACK COVER ═══ (photo only) -->
  </div>
</template>

<style lang="scss" scoped>
// -- Front Cover --

.cover-dimmed {
  filter: brightness(0.55);
}

.front-text {
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--page-inset-y) 4rem;
  gap: var(--gap-md);
  background: radial-gradient(ellipse at center, rgba(0, 0, 0, 0.35) 0%, transparent 70%);
}

.front-date {
  font-size: var(--type-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-wider);
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.8);
  text-shadow:
    0 1px 3px rgba(0, 0, 0, 0.8),
    0 0 12px rgba(0, 0, 0, 0.6),
    0 0 30px rgba(0, 0, 0, 0.4);
}

.front-title {
  font-size: var(--display-1);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: -0.03em;
  color: white;
  text-align: center;
  max-width: 85%;
  text-shadow:
    0 2px 4px rgba(0, 0, 0, 0.9),
    0 0 20px rgba(0, 0, 0, 0.7),
    0 0 60px rgba(0, 0, 0, 0.5);
}

.front-subtitle {
  font-size: var(--type-subtitle);
  font-weight: 300;
  letter-spacing: var(--tracking-wide);
  color: rgba(255, 255, 255, 0.85);
  text-align: center;
  max-width: 70%;
  text-shadow:
    0 1px 3px rgba(0, 0, 0, 0.8),
    0 0 12px rgba(0, 0, 0, 0.6),
    0 0 30px rgba(0, 0, 0, 0.4);
}

// -- Shared --

.cover-rule {
  width: 2.5rem;
  height: 1px;
  background: rgba(255, 255, 255, 0.3);
  flex-shrink: 0;
}

.cover-picker-anchor {
  position: absolute;
  top: var(--gap-md);
  left: var(--gap-md);
  z-index: 3;
  zoom: calc(1 / var(--editor-zoom, 1));
}
</style>
