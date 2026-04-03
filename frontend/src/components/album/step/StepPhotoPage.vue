<script lang="ts" setup>
import { computed, ref, watch } from "vue";
import { useDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { isPortrait as isPortraitMedia } from "@/utils/media";

const { mediaByName } = useAlbum();
const printMode = usePrintMode();

const props = defineProps<{
  page: string[];
}>();

const emit = defineEmits<{
  "update:page": [page: string[]];
}>();
const isPortrait = (name: string) => {
  const m = mediaByName.value.get(name);
  return m ? isPortraitMedia(m) : false;
};

/**
 * Mixed layouts depend on orientation ordering:
 * - 1P+2L / 1P+3L: portrait must be first (spans all rows on the left).
 * - 2P+1L: landscape must be last (spans full bottom row).
 */
function enforceOrientationOrder(page: string[]): string[] {
  if (page.length !== 3 && page.length !== 4) return page;
  const portraits = page.filter(isPortrait);
  const landscapes = page.filter((m) => !isPortrait(m));
  if (portraits.length === 1) return [portraits[0]!, ...landscapes];
  if (portraits.length === 2 && page.length === 3) return [...portraits, landscapes[0]!];
  return page;
}

/** Local copy for instant drag feedback. Syncs from prop on external changes. */
const localPage = ref(enforceOrientationOrder([...props.page]));
watch(() => props.page, (val) => {
  const enforced = enforceOrientationOrder(val);
  if (enforced.length === localPage.value.length &&
      enforced.every((v, i) => v === localPage.value[i])) return;
  localPage.value = [...enforced];
});

const containerRef = ref<HTMLElement | null>(null);

function syncPage() {
  localPage.value = enforceOrientationOrder(localPage.value);
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

const layoutClass = computed(() => {
  const page = localPage.value;
  if (page.length >= 5) return `layout-${page.length}`;
  const p = page.filter(isPortrait).length;
  const l = page.length - p;
  return `layout-${p}p-${l}l`;
});
</script>

<template>
  <div class="page page-container">
    <div ref="containerRef" :class="['container', layoutClass]">
      <MediaItem
        v-for="photo in localPage"
        :key="photo"
        :media="photo"
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
  padding: var(--photo-gap-lg);
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
