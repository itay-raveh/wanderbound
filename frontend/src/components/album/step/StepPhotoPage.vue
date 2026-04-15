<script lang="ts" setup>
import { computed, ref, watch } from "vue";
import { useDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { isPortraitByName } from "@/utils/media";
import {
  enforceOrientationOrder,
  photoPageFraction,
  resolveLayoutClass,
} from "@/utils/photoLayout";
import { mediaQuality } from "@/utils/photoQuality";

const { mediaByName } = useAlbum();
const printMode = usePrintMode();

const props = defineProps<{
  page: string[];
}>();

const emit = defineEmits<{
  "update:page": [page: string[]];
}>();
const isPortrait = (name: string) => isPortraitByName(name, mediaByName.value);

/** Local copy for instant drag feedback. Syncs from prop on external changes. */
const localPage = ref(enforceOrientationOrder([...props.page], isPortrait));
watch(
  () => props.page,
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

function syncPage() {
  localPage.value = enforceOrientationOrder(localPage.value, isPortrait);
  emit("update:page", [...localPage.value]);
}

if (!printMode) {
  useDraggable(containerRef, localPage, {
    group: "photos",
    animation: 200,
    onUpdate: syncPage,
    onAdd: syncPage,
  });
}

const layoutClass = computed(() =>
  resolveLayoutClass(localPage.value, isPortrait),
);

const photoQualities = computed(() =>
  localPage.value.map((name, i) =>
    mediaQuality(
      name,
      photoPageFraction(layoutClass.value, i),
      mediaByName.value,
    ),
  ),
);
</script>

<template>
  <div class="page page-container">
    <div ref="containerRef" :class="['container', layoutClass]">
      <MediaItem
        v-for="(photo, i) in localPage"
        :key="photo"
        :media="photo"
        :quality="photoQualities[i]"
        class="item"
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

// -- Default: cover. Layouts that need contain opt out. --

.container :deep(img) {
  object-fit: cover;
}

// -- 1 photo: contain (show full image) --

.layout-1p-0l,
.layout-0p-1l {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;

  :deep(img) {
    object-fit: contain;
  }
}

// -- 2 photos --

.layout-0p-2l,
.layout-1p-1l {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;

  :deep(img) {
    object-fit: contain;
  }
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

  :deep(img) {
    object-fit: contain;
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

  :deep(img) {
    object-fit: contain;
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
