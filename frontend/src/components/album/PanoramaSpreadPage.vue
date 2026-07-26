<script lang="ts" setup>
import type { AlbumMedia, PanoramaDestination } from "@/client";
import {
  computed,
  defineAsyncComponent,
  onBeforeUnmount,
  onMounted,
  ref,
} from "vue";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { t } from "@/i18n";
import { panoramaRenditionSize } from "@/utils/media";
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
const EDITOR_RENDER_WIDTH = 2048;
const PRINT_RENDER_WIDTH = 8192;
const pageRef = ref<HTMLElement | null>(null);
const measuredWidth = ref(0);
const measuredHeight = ref(0);
let placementObserver: ResizeObserver | null = null;

function updatePlacementSize(entry?: ResizeObserverEntry): void {
  const contentBox = entry?.contentBoxSize?.[0];
  const bounds = pageRef.value?.getBoundingClientRect();
  const contentWidth =
    contentBox?.inlineSize ||
    entry?.contentRect.width ||
    pageRef.value?.clientWidth ||
    bounds?.width;
  const contentHeight =
    contentBox?.blockSize ||
    entry?.contentRect.height ||
    pageRef.value?.clientHeight ||
    bounds?.height;
  if (!contentWidth || !contentHeight) return;
  measuredWidth.value = contentWidth * 2;
  measuredHeight.value = contentHeight;
}

onMounted(() => {
  updatePlacementSize();
  if (typeof ResizeObserver === "undefined" || !pageRef.value) return;
  placementObserver = new ResizeObserver(([entry]) =>
    updatePlacementSize(entry),
  );
  placementObserver.observe(pageRef.value);
});
onBeforeUnmount(() => placementObserver?.disconnect());

const editorRendition = computed(() =>
  panoramaRenditionSize(
    measuredWidth.value || EDITOR_RENDER_WIDTH,
    measuredHeight.value ||
      Math.round(
        (EDITOR_RENDER_WIDTH * PAGE_HEIGHT_MM) / (PAGE_WIDTH_MM * 2),
      ),
    window.devicePixelRatio,
  ),
);
const width = computed(() =>
  printMode ? PRINT_RENDER_WIDTH : editorRendition.value.width,
);
const height = computed(() =>
  printMode
    ? Math.round((width.value * PAGE_HEIGHT_MM) / (PAGE_WIDTH_MM * 2))
    : editorRendition.value.height,
);
const albumMedia = computed(() => mediaByName.value.get(props.media));
const src = computed(() => {
  return placementMediaUrl(props.media, width.value, height.value);
});
const dialogOpen = ref(false);
const destination = computed<PanoramaDestination>(() => ({
  kind: "panorama_spread",
  aspect_ratio: width.value / height.value,
  width_px: width.value,
  height_px: height.value,
}));
</script>

<template>
  <div
    ref="pageRef"
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
      :destination="destination"
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
