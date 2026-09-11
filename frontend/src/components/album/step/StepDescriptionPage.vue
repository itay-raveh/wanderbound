<script lang="ts" setup>
import AlbumPage from "@/components/album/AlbumPage.vue";
import type { TextPage } from "@/composables/useTextLayout";
import { useAlbum } from "@/composables/useAlbum";
import { mediaQuality, PHOTO_PANEL_FRACTION } from "@/utils/photoQuality";
import EditableText from "../EditableText.vue";
import MediaItem from "../MediaItem.vue";
import { computed } from "vue";

const { mediaByName, mediaResolutionWarningPreset } = useAlbum();

const props = defineProps<{
  page: TextPage;
  description: string;
  photo: string | null;
}>();

const emit = defineEmits<{
  "update:description": [description: string];
}>();

const photoQuality = computed(() =>
  props.photo
    ? mediaQuality(
        props.photo,
        PHOTO_PANEL_FRACTION,
        "cover",
        mediaByName.value,
        mediaResolutionWarningPreset.value,
      )
    : null,
);
</script>

<template>
  <AlbumPage
    :number-placement="photo ? 'image' : 'margin'"
    class="description-page"
  >
    <EditableText
      :model-value="description"
      multiline
      class="description-text"
      :page="page"
      @update:model-value="emit('update:description', $event)"
    />
    <MediaItem
      v-if="photo"
      :media="photo"
      fit-cover
      :quality="photoQuality"
      class="description-photo"
    />
    <div v-else class="topo-filler" />
  </AlbumPage>
</template>

<style lang="scss" scoped>
:deep(.description-page) {
  display: flex;
  color: var(--text);
  overflow: visible;
}

.description-text {
  flex: 0 0 var(--meta-width);
  padding: var(--page-inset-y) var(--page-inset-y) var(--page-inset-y)
    var(--page-inset-x);
  font-family: var(--font-album-body);
  font-size: var(--type-xs);
  line-height: 1.65;
  white-space: pre-wrap;
  text-align: start;
  overflow-wrap: break-word;
  hyphens: none;
  overflow: hidden;
  box-sizing: border-box;
}

.description-photo {
  margin-block: calc(-1 * var(--bleed));
  margin-inline-end: calc(-1 * var(--bleed));
  height: calc(100% + 2 * var(--bleed));
  flex: 1;
  min-height: 0;
  cursor: default;
}

.topo-filler {
  margin-block: calc(-1 * var(--bleed));
  margin-inline-end: calc(-1 * var(--bleed));
  flex: 1;
  min-height: 0;
  background: url("/topo-contours.svg") center / cover no-repeat;
  print-color-adjust: exact;
}
</style>
