<script lang="ts" setup>
import { computed } from "vue";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { mediaUrl } from "@/utils/media";
import { PAGE_HEIGHT_MM, PAGE_WIDTH_MM } from "@/utils/pageSize";

const props = defineProps<{
  media: string;
  side: "left" | "right";
}>();

const { albumId, mediaByName } = useAlbum();
const printMode = usePrintMode();
const EDITOR_RENDER_WIDTH = 2048;
const PRINT_RENDER_WIDTH = 8192;
const width = printMode ? PRINT_RENDER_WIDTH : EDITOR_RENDER_WIDTH;
const height = Math.round((width * PAGE_HEIGHT_MM) / (PAGE_WIDTH_MM * 2));
const src = computed(() => {
  const base = mediaUrl(props.media, albumId.value);
  const revision = mediaByName.value.get(props.media)?.panorama?.revision;
  if (revision == null) return base;
  const query = new URLSearchParams({
    w: String(width),
    h: String(height),
    panorama_revision: String(revision),
  });
  return `${base}?${query}`;
});
</script>

<template>
  <div :class="['page-container', 'panorama-page', `side-${side}`]">
    <img
      :src="src"
      alt=""
      class="panorama-media"
      :loading="printMode ? 'eager' : 'lazy'"
      decoding="async"
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
