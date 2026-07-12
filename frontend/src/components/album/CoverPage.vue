<script lang="ts" setup>
import { parseLocalDate } from "@/utils/date";
import type { AlbumChapter, AlbumMeta, StepRead as Step } from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useAlbum } from "@/composables/useAlbum";
import { mediaQuality, COVER_FRACTION } from "@/utils/photoQuality";
import EditableText from "./EditableText.vue";
import MediaItem from "./MediaItem.vue";
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { formatDateRange } = useUserQuery();
const { t } = useI18n();
const { mediaByName, mediaResolutionWarningPreset } = useAlbum();

const props = defineProps<{
  album: AlbumMeta;
  chapter: AlbumChapter;
  steps: Step[];
  isBack?: boolean;
}>();

const albumMutation = useAlbumMutation(() => props.album.id);

const coverMedia = computed(() =>
  props.isBack
    ? props.chapter.back_cover_photo
    : props.chapter.front_cover_photo,
);

const coverQuality = computed(() =>
  coverMedia.value
    ? mediaQuality(
        coverMedia.value,
        COVER_FRACTION,
        mediaByName.value,
        mediaResolutionWarningPreset.value,
      )
    : null,
);

const dates = computed(() => {
  const start = parseLocalDate(props.steps[0].datetime);
  const end = parseLocalDate(props.steps[props.steps.length - 1].datetime);
  return formatDateRange(start, end, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
});

function saveText(field: "title" | "subtitle", value: string) {
  albumMutation.mutate({
    chapters: (props.album.chapters ?? []).map((chapter) =>
      chapter.id === props.chapter.id ? { ...chapter, [field]: value } : chapter,
    ),
  });
}
</script>

<template>
  <div class="page-container cover-page relative-position">
    <!-- Background photo (full bleed, no uniform dimming) -->
    <MediaItem
      v-if="coverMedia"
      :media="coverMedia"
      fit-cover
      :quality="coverQuality"
      :class="['fit', { 'cover-dimmed': !isBack }]"
    />

    <!-- ═══ FRONT COVER ═══ -->
    <template v-if="!isBack">
      <div class="front-text absolute-full">
        <div dir="auto" class="front-date">{{ dates }}</div>
        <div class="cover-rule" aria-hidden="true" />

        <EditableText
          :model-value="chapter.title"
          :placeholder="t('album.chapterTitlePlaceholder')"
          dir="auto"
          class="front-title"
          @update:model-value="saveText('title', $event)"
        />

        <EditableText
          :model-value="chapter.subtitle"
          :placeholder="t('album.chapterSubtitlePlaceholder')"
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

// Dark overlay instead of filter: brightness() - filters break in Chromium's PDF backend.
.cover-dimmed::after {
  content: "";
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  pointer-events: none;
}

.front-text {
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--page-inset-y) var(--page-inset-x);
  gap: var(--gap-md);
  background: radial-gradient(
    ellipse at center,
    rgba(0, 0, 0, 0.35) 0%,
    transparent 70%
  );
  pointer-events: none;
}

.front-date {
  font-size: var(--type-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-wider);
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.8);
}

.front-title {
  font-size: var(--display-1);
  font-weight: 800;
  line-height: 1.05;
  letter-spacing: var(--tracking-tight);
  color: white;
  text-align: center;
  text-wrap: balance;
  max-width: 85%;
  min-width: 9rem;
  min-height: 1.1em;
  pointer-events: auto;
}

.front-subtitle {
  font-size: var(--type-subtitle);
  font-weight: 300;
  letter-spacing: var(--tracking-wide);
  color: rgba(255, 255, 255, 0.85);
  text-align: center;
  text-wrap: balance;
  max-width: 70%;
  min-width: 7rem;
  min-height: 1.2em;
  pointer-events: auto;
}

// -- Shared --

.cover-rule {
  width: 2.5rem;
  height: 0.125rem;
  background: rgba(255, 255, 255, 0.5);
  flex-shrink: 0;
}
</style>
