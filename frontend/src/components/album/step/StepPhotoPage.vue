<script lang="ts" setup>
import {
  clearDraggedPhoto,
  draggedPhoto,
  draggedSourceCallback,
} from "@/utils/dragState";
import { ref } from "vue";
import MediaItem from "../layouts/MediaItem.vue";

const props = defineProps<{
  page: string[];
  stepId: number;
  albumName: string;
}>();

const emit = defineEmits<{
  "update:page": [page: string[]];
}>();

const isDragOver = ref(false);

function removePhoto(photoToRemove: string) {
  const newPage = [...props.page];
  const idx = newPage.findIndex((p) => p === photoToRemove);
  if (idx >= 0) {
    newPage.splice(idx, 1);
    emit("update:page", newPage);
  }
}

function insertPhoto(data: {
  targetPhoto: string;
  photo: string;
  position: "before" | "after";
}) {
  const newPage = [...props.page];
  const targetIdx = newPage.findIndex((p) => p === data.targetPhoto);
  if (targetIdx >= 0) {
    const insertIdx = data.position === "before" ? targetIdx : targetIdx + 1;
    newPage.splice(insertIdx, 0, data.photo);
    emit("update:page", newPage);
  }
}

function onDropPage(e: DragEvent) {
  isDragOver.value = false;
  if (!draggedPhoto) return;

  if (!(e.target as HTMLElement).closest(".media-item")) {
    const newPage = [...props.page, draggedPhoto];
    if (draggedSourceCallback) draggedSourceCallback();
    clearDraggedPhoto();
    emit("update:page", newPage);
  }
}
</script>

<template>
  <div
    :class="{ 'drag-over': isDragOver }"
    class="page page-container"
    @dragover.prevent="isDragOver = true"
    @dragleave.prevent="isDragOver = false"
    @drop.prevent="onDropPage"
  >
    <div class="container">
      <MediaItem
        v-for="photo in page"
        :key="photo"
        :album-name="albumName"
        :media="photo"
        :step-id="stepId"
        class="item"
        @remove-self="removePhoto(photo)"
        @insert-at="
          insertPhoto({
            targetPhoto: photo,
            photo: $event.photo,
            position: $event.position,
          })
        "
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
  gap: 5mm;
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
  column-gap: 5mm;
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
  column-gap: 5mm;
  row-gap: 2mm;
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
  gap: 3mm;
}

.container:has(.item:nth-child(5):last-child) {
  grid-template-columns: 2fr 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  column-gap: 5mm;
  row-gap: 2mm;
}

.container:has(.item:nth-child(5):last-child) .item:first-child {
  grid-row: 1 / 3;
}

.container:has(.item:nth-child(6):last-child) {
  grid-template-columns: 2fr 1fr 1fr;
  grid-template-rows: 1fr 1fr 1fr;
  column-gap: 4mm;
  row-gap: 2mm;
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

.image {
  max-width: 100%;
  max-height: 100%;
}
</style>
