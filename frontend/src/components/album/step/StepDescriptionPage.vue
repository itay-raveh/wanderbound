<script lang="ts" setup>
import type { JustifiedLine } from "@/composables/useTextLayout";
import { useAlbum } from "@/composables/useAlbum";
import { mediaQuality, PHOTO_PANEL_FRACTION } from "@/utils/photoQuality";
import EditableText from "../EditableText.vue";
import MediaItem from "../MediaItem.vue";
import { computed } from "vue";

const { mediaByName, mediaResolutionWarningPreset } = useAlbum();

const props = defineProps<{
  lines: JustifiedLine[];
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
        mediaByName.value,
        mediaResolutionWarningPreset.value,
      )
    : null,
);
</script>

<template>
  <div class="page-container description-page">
    <EditableText
      :model-value="description"
      multiline
      dir="auto"
      class="description-text"
      :lines="lines"
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
  </div>
</template>

<style lang="scss" scoped>
.description-page {
  display: flex;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
}

.description-text {
  flex: 0 0 var(--meta-width);
  padding: var(--page-inset-y) var(--page-inset-y) var(--page-inset-y)
    var(--page-inset-x);
  font-family: var(--font-album-body);
  font-size: var(--type-xs);
  line-height: 1.65;
  white-space: pre-wrap;
  text-align: justify;
  overflow: hidden;
  box-sizing: border-box;
}

.description-photo {
  flex: 1;
  min-height: 0;
  cursor: default;
}

.topo-filler {
  flex: 1;
  min-height: 0;
  background: url("/topo-contours.svg") center / cover no-repeat;
  print-color-adjust: exact;
}
</style>
