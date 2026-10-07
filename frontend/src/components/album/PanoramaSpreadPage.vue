<script lang="ts" setup>
import AlbumPage from "@/components/album/AlbumPage.vue";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMediaReady, usePrintMode } from "@/composables/usePrintReady";
import { usePanoramaFrame } from "@/composables/usePanoramaFrame";
import { computed } from "vue";
import PanoramaActions from "./PanoramaActions.vue";

const props = defineProps<{
  media: string;
  side: "left" | "right";
}>();

const emit = defineEmits<{
  "make-full-page": [media: string];
}>();

const { placementMediaUrl, pageSize } = useAlbum();
const openPanoramaDialog = usePanoramaFrame();
const printMode = usePrintMode();
const printMediaReady = usePrintMediaReady();
const spreadAspectRatio = computed(
  () => (pageSize.value.widthMm * 2) / pageSize.value.heightMm,
);
const src = computed(() => placementMediaUrl(props.media));
const renderedSrc = computed(() =>
  printMode && !printMediaReady.value ? undefined : src.value,
);

function openPanoramaFrame(): void {
  openPanoramaDialog?.({
    media: props.media,
    aspectRatio: spreadAspectRatio.value,
    showSeam: true,
  });
}
</script>

<template>
  <AlbumPage
    number-placement="image"
    :class="['panorama-page', `side-${side}`]"
    :data-media="media"
  >
    <img
      :src="renderedSrc"
      alt=""
      class="panorama-media"
      :loading="printMode ? 'eager' : 'lazy'"
      decoding="async"
    />
    <PanoramaActions
      v-if="!printMode && side === 'left'"
      :media="media"
      make-full-page
      @frame="openPanoramaFrame"
      @make-full-page="emit('make-full-page', $event)"
    />
  </AlbumPage>
</template>

<style lang="scss" scoped>
:deep(.panorama-page) {
  position: relative;
  overflow: visible;
}

.panorama-media {
  position: absolute;
  top: calc(-1 * var(--bleed));
  left: calc(-1 * var(--bleed));
  width: calc(2 * var(--page-width) + 2 * var(--bleed));
  height: calc(var(--page-height) + 2 * var(--bleed));
  object-fit: cover;
}

.side-right .panorama-media {
  left: calc(-1 * var(--page-width) - var(--bleed));
}
</style>
