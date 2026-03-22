<script lang="ts" setup>
import { computed } from "vue";
import { VueDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";
import { useAlbum } from "@/composables/useAlbum";
import { useLocalCopy } from "@/composables/useLocalCopy";

const { media } = useAlbum();

const props = defineProps<{
  page: string[];
}>();

const emit = defineEmits<{
  "update:page": [page: string[]];
}>();

const isPortrait = (m: string) => media.value[m] === "p";

/** In 1P+2L and 1P+3L layouts the portrait must be first (it spans all rows). */
function enforcePortraitFirst(page: string[]): string[] {
  if (page.length !== 3 && page.length !== 4) return page;
  if (isPortrait(page[0]!)) return page;
  const portrait = page.find(isPortrait);
  if (!portrait) return page;
  // Multiple portraits use a symmetric grid — reordering would be arbitrary
  if (page.filter(isPortrait).length !== 1) return page;
  return [portrait, ...page.filter((m) => m !== portrait)];
}

const localPage = useLocalCopy(() => enforcePortraitFirst(props.page));

function emitPage() {
  localPage.value = enforcePortraitFirst(localPage.value);
  emit("update:page", [...localPage.value]);
}

const layoutClass = computed(() => {
  const page = localPage.value;
  // 5+ photos use the same grid regardless of orientation mix
  if (page.length >= 5) return `layout-${page.length}`;
  const p = page.filter(isPortrait).length;
  const l = page.length - p;
  return `layout-${p}p-${l}l`;
});
</script>

<template>
  <div class="page page-container">
    <VueDraggable
      v-model="localPage"
      :class="['container', layoutClass]"
      group="photos"
      :animation="200"
      @update="emitPage"
      @add="emitPage"
    >
      <MediaItem
        v-for="photo in localPage"
        :key="photo"
        :media="photo"
        class="item"
      />
    </VueDraggable>
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
