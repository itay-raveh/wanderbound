<script lang="ts" setup>
import { computed, ref, watch } from "vue";
import { useDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { isPortraitByName } from "@/utils/media";
import { useElementVisibility } from "@vueuse/core";
import {
  enforceOrientationOrder,
  photoPageFit,
  photoPageFraction,
  resolveLayoutClass,
} from "@/utils/photoLayout";
import { mediaQuality } from "@/utils/photoQuality";
import type { StepPageLayout } from "@/client";

const { mediaByName, mediaResolutionWarningPreset } = useAlbum();
const printMode = usePrintMode();

const props = defineProps<{
  page: StepPageLayout;
}>();

const emit = defineEmits<{
  "update:page": [page: StepPageLayout];
  "make-full-page": [media: string];
  "make-panorama-spread": [media: string];
}>();
const isPortrait = (name: string) => isPortraitByName(name, mediaByName.value);

/** Local copy for instant drag feedback. Syncs from prop on external changes. */
const localPage = ref(
  enforceOrientationOrder([...props.page.media], isPortrait),
);
watch(
  () => props.page.media,
  (val) => {
    const enforced = enforceOrientationOrder(val, isPortrait);
    if (
      enforced.length === localPage.value.length &&
      enforced.every((v, i) => v === localPage.value[i])
    )
      return;
    localPage.value = [...enforced];
  },
);

const containerRef = ref<HTMLElement | null>(null);
const pageVisible = useElementVisibility(containerRef, {
  rootMargin: "800px",
  initialValue: printMode,
});

function syncPage() {
  localPage.value = enforceOrientationOrder(localPage.value, isPortrait);
  emit("update:page", { ...props.page, media: [...localPage.value] });
}

if (!printMode) {
  const sortable = useDraggable(containerRef, localPage, {
    group: "photos",
    animation: 0,
    immediate: false,
    onUpdate: syncPage,
    onAdd: syncPage,
  });
  let sortableActive = false;

  watch(
    pageVisible,
    (visible) => {
      if (visible && !sortableActive) {
        sortable.start();
        sortableActive = true;
      } else if (!visible && sortableActive) {
        sortable.destroy();
        sortableActive = false;
      }
    },
    { immediate: true },
  );
}

const layoutClass = computed(() =>
  resolveLayoutClass(localPage.value, isPortrait),
);
const photoFit = computed(() => photoPageFit(layoutClass.value));
const fullBleedPanorama = computed(() => {
  const media = localPage.value.length === 1 ? localPage.value[0] : undefined;
  return media != null && mediaByName.value.get(media)?.panorama != null;
});

const photoQualities = computed(() =>
  localPage.value.map((name, i) =>
    mediaQuality(
      name,
      photoPageFraction(layoutClass.value, i),
      photoFit.value,
      mediaByName.value,
      mediaResolutionWarningPreset.value,
    ),
  ),
);
</script>

<template>
  <div class="page page-container">
    <div
      ref="containerRef"
      :class="[
        'container',
        layoutClass,
        `fit-${photoFit}`,
        { 'full-bleed-panorama': fullBleedPanorama },
      ]"
    >
      <MediaItem
        v-for="(photo, i) in localPage"
        :key="photo"
        :media="photo"
        :quality="photoQualities[i]"
        :panorama-destination-kind="
          localPage.length === 1 ? 'full_page' : 'grid'
        "
        :make-full-page="localPage.length > 1"
        :make-panorama-spread="localPage.length === 1"
        class="item"
        @make-full-page="emit('make-full-page', $event)"
        @make-panorama-spread="emit('make-panorama-spread', $event)"
      />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.page {
  display: flex;
  align-items: center;
  justify-content: center;
}

.container {
  width: 100%;
  height: 100%;
  display: grid;
  gap: var(--photo-gap-lg);
  padding: max(var(--photo-gap-lg), var(--safe-margin, 0mm));
  align-items: stretch;
  justify-items: stretch;
  box-sizing: border-box;
}

.item {
  display: flex;
  align-items: center;
  justify-content: center;
}

.container :deep(img) {
  object-fit: cover;
}

.container.fit-contain :deep(img) {
  object-fit: contain;
}

.container.full-bleed-panorama {
  gap: 0;
  padding: 0;
}

.container.full-bleed-panorama :deep(img) {
  object-fit: cover;
}

// -- 1 photo --

.layout-1p-0l,
.layout-0p-1l {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

// -- 2 photos --

.layout-0p-2l,
.layout-1p-1l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}

.layout-2p-0l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}

// -- 3 photos: all same orientation --

.layout-3p-0l {
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: min-content;
  align-content: center;

  .item {
    aspect-ratio: 9 / 16;
    overflow: hidden;
  }
}

.layout-0p-3l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;

  .item:first-child {
    grid-row: 1 / 3;
  }
}

// -- 3 photos: mixed (portraits sorted first) --

.layout-1p-2l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;

  .item:first-child {
    grid-row: 1 / 3;
  }
}

.layout-2p-1l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;

  .item:last-child {
    grid-column: 1 / 3;
  }
}

// -- 4 photos --

.layout-0p-4l,
.layout-2p-2l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

.layout-1p-3l {
  grid-template-columns: auto auto;
  grid-template-rows: 1fr 1fr 1fr;
  justify-content: center;

  .item:first-child {
    grid-row: 1 / 4;
    aspect-ratio: 3 / 4;
    overflow: hidden;
  }

  .item:not(:first-child) {
    aspect-ratio: 16 / 9;
    overflow: hidden;
  }
}

.layout-3p-1l,
.layout-4p-0l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

// -- 5 photos --

.layout-5 {
  grid-template-columns: 2fr 1fr 1fr;
  grid-template-rows: 1fr 1fr;

  .item:first-child {
    grid-row: 1 / 3;
  }
}

// -- 6 photos --

.layout-6 {
  grid-template-columns: 2fr 1fr 1fr;
  grid-template-rows: 1fr 1fr 1fr;

  .item:first-child {
    grid-row: 1 / 4;
  }
}
</style>
