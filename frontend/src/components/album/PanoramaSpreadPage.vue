<script lang="ts" setup>
import type { AlbumMedia } from "@/client";
import { computed, defineAsyncComponent, ref } from "vue";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { t } from "@/i18n";
import { PAGE_HEIGHT_MM, PAGE_WIDTH_MM } from "@/utils/pageSize";

const PanoramaFrameDialog = defineAsyncComponent(() =>
  import("@/components/editor/PanoramaFrameDialog.vue").then(
    (module) => module.default,
  ),
);

const props = defineProps<{
  media: string;
  side: "left" | "right";
}>();

const emit = defineEmits<{
  "make-full-page": [media: string];
}>();

const { albumId, mediaByName, placementMediaUrl } = useAlbum();
const printMode = usePrintMode();
const spreadAspectRatio = (PAGE_WIDTH_MM * 2) / PAGE_HEIGHT_MM;
const albumMedia = computed(() => mediaByName.value.get(props.media));
const src = computed(() => placementMediaUrl(props.media));
const dialogOpen = ref(false);
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
    <div v-if="!printMode && side === 'left'" class="panorama-actions">
      <button
        type="button"
        class="panorama-frame-action panorama-action"
        @click="dialogOpen = true"
      >
        {{ t("panorama.frame.title") }}
      </button>
      <button
        type="button"
        class="panorama-full-page-action panorama-action"
        @click="emit('make-full-page', media)"
      >
        {{ t("panorama.makeFullPage") }}
      </button>
    </div>
    <PanoramaFrameDialog
      v-if="dialogOpen && albumMedia"
      v-model="dialogOpen"
      :album-id="albumId"
      :media="albumMedia as AlbumMedia"
      :aspect-ratio="spreadAspectRatio"
      show-seam
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

.panorama-actions {
  position: absolute;
  z-index: 2;
  inset-block-start: var(--gap-md);
  inset-inline-start: var(--gap-md);
  display: flex;
  gap: var(--gap-sm);
}

.panorama-action {
  min-height: 2.75rem;
  padding: var(--gap-sm) var(--gap-md-lg);
  border: 1px solid var(--q-primary);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--q-primary);
  cursor: pointer;
  font: inherit;
  font-size: var(--type-sm);
  font-weight: 600;
}
</style>
