<script lang="ts" setup>
import { computed } from "vue";
import { VueDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";
import { useAlbum } from "@/composables/useAlbum";
import { useLocalCopy } from "@/composables/useLocalCopy";

const { orientations } = useAlbum();

const props = defineProps<{
  page: string[];
  stepId: number;
}>();

const emit = defineEmits<{
  "update:page": [page: string[]];
}>();

const localPage = useLocalCopy(() => props.page);

function emitPage() {
  emit("update:page", [...localPage.value]);
}

const layoutClass = computed(() => {
  if (localPage.value.length !== 3) return "";
  const o = localPage.value.map((m) => orientations.value[m]);
  if (o.every((v) => v === "p")) return "three-portraits";
  if (o[0] === "p" && o[1] === "l" && o[2] === "l") return "one-portrait-two-landscapes";
  return "";
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
        :step-id="stepId"
        :cols="localPage.length === 1 ? 1 : 2"
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
  align-items: stretch;
  justify-items: stretch;
}

.container:has(.item:nth-child(1):last-child) {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

.container:has(.item:nth-child(2):last-child) {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}

.container.three-portraits {
  grid-template-columns: 1fr 1fr 1fr !important;
  grid-template-rows: 1fr !important;
  column-gap: var(--photo-gap-lg);
  row-gap: 0 !important;
}

.container.three-portraits .item:first-child {
  grid-row: auto !important;
  grid-column: auto !important;
}

.container.one-portrait-two-landscapes {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

.container.one-portrait-two-landscapes .item:first-child {
  grid-row: 1 / 3;
}

.container.one-portrait-two-landscapes :deep(.image) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.container.one-portrait-two-landscapes :deep(.video-wrapper) {
  width: 100% !important;
  height: 100% !important;
}

.container:has(.item:nth-child(3):last-child):not(
    .three-portraits,
    .one-portrait-two-landscapes
  ) {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  column-gap: var(--photo-gap-lg);
  row-gap: var(--photo-gap-xs);
}

.container:has(.item:nth-child(3):last-child):not(
    .three-portraits,
    .one-portrait-two-landscapes
  )
  .item:first-child {
  grid-row: 1 / 3;
}

.container:has(.item:nth-child(4):last-child) {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: var(--photo-gap-sm);
}

.container:has(.item:nth-child(5):last-child) {
  grid-template-columns: 2fr 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  column-gap: var(--photo-gap-lg);
  row-gap: var(--photo-gap-xs);
}

.container:has(.item:nth-child(5):last-child) .item:first-child {
  grid-row: 1 / 3;
}

.container:has(.item:nth-child(6):last-child) {
  grid-template-columns: 2fr 1fr 1fr;
  grid-template-rows: 1fr 1fr 1fr;
  column-gap: var(--photo-gap-md);
  row-gap: var(--photo-gap-xs);
}

.container:has(.item:nth-child(6):last-child) .item:first-child {
  grid-row: 1 / 4;
}

.item {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

</style>
