<script lang="ts" setup>
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { usePanoramaFrame } from "@/composables/usePanoramaFrame";
import { PAGE_HEIGHT_MM, PAGE_WIDTH_MM } from "@/utils/pageSize";
import { computed } from "vue";
import PanoramaActions from "./PanoramaActions.vue";

const props = defineProps<{
  media: string;
  side: "left" | "right";
}>();

const emit = defineEmits<{
  "make-full-page": [media: string];
}>();

const { placementMediaUrl } = useAlbum();
const openPanoramaDialog = usePanoramaFrame();
const printMode = usePrintMode();
const spreadAspectRatio = (PAGE_WIDTH_MM * 2) / PAGE_HEIGHT_MM;
const src = computed(() => placementMediaUrl(props.media));

function openPanoramaFrame(): void {
  openPanoramaDialog?.({
    media: props.media,
    aspectRatio: spreadAspectRatio,
    showSeam: true,
  });
}
</script>

<template>
  <div
    :class="['page-container', 'panorama-page', `side-${side}`]"
    :data-media="media"
  >
    <img
      :src="src"
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
  </div>
</template>

<style lang="scss" scoped>
.panorama-page {
  position: relative;
  overflow: hidden;
}

.panorama-media {
  position: absolute;
  top: 0;
  left: 0;
  width: 200%;
  height: 100%;
  object-fit: cover;
}

.side-right .panorama-media {
  left: -100%;
}

</style>
