<script lang="ts" setup>
import { ref, watch } from "vue";
import { VueDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";

const props = defineProps<{
  page: string[];
  stepId: number;
  albumId: string;
}>();

const emit = defineEmits<{
  "update:page": [page: string[]];
}>();

const localPage = ref([...props.page]);

watch(
  () => props.page,
  (val) => {
    localPage.value = [...val];
  },
);

function onDragChange() {
  emit("update:page", [...localPage.value]);
}
</script>

<template>
  <div class="page page-container">
    <VueDraggable
      v-model="localPage"
      class="container"
      group="photos"
      :animation="200"
      @change="onDragChange"
    >
      <MediaItem
        v-for="photo in localPage"
        :key="photo"
        :albumId="albumId"
        :media="photo"
        :stepId="stepId"
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
  gap: var(--gap-color-size, 5mm);
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
