<script lang="ts" setup>
import {
  clearDraggedPhoto,
  draggedPhoto,
  draggedSourceCallback,
} from "@/utils/dragState";
import { ref } from "vue";
import MediaItem from "../layouts/MediaItem.vue";

const props = defineProps<{
  assets: Array<string>;
  stepId: number;
  albumName: string;
}>();

const emit = defineEmits<{
  "update:unused": [unused: string[]];
}>();

const isDragOver = ref(false);

function removeUnused(photoToRemove: string) {
  if (!props.assets) return;
  const newUnused = [...props.assets];
  const idx = newUnused.findIndex((p) => p === photoToRemove);
  if (idx >= 0) {
    newUnused.splice(idx, 1);
    emit("update:unused", newUnused);
  }
}

function insertUnused(data: {
  targetPhoto: string;
  photo: string;
  position: "before" | "after";
}) {
  if (!props.assets) return;
  const newUnused = [...props.assets];
  const targetIdx = newUnused.findIndex((p) => p === data.targetPhoto);
  if (targetIdx >= 0) {
    const insertIdx = data.position === "before" ? targetIdx : targetIdx + 1;
    newUnused.splice(insertIdx, 0, data.photo);
    emit("update:unused", newUnused);
  }
}

function onDropUnused(e: DragEvent) {
  isDragOver.value = false;
  if (!draggedPhoto || !props.assets) return;

  if (!(e.target as HTMLElement).closest(".media-item")) {
    const newUnused = [...props.assets, draggedPhoto];
    if (draggedSourceCallback) draggedSourceCallback();
    clearDraggedPhoto();
    emit("update:unused", newUnused);
  }
}
</script>

<template>
  <div class="wrapper">
    <div class="header">Unused Photos</div>
    <div
      :class="{ 'drag-over': isDragOver }"
      class="container"
      @dragover.prevent="isDragOver = true"
      @dragleave.prevent="isDragOver = false"
      @drop.prevent="onDropUnused"
    >
      <MediaItem
        v-for="photo in assets"
        :key="photo"
        :album-name="albumName"
        :media="photo"
        :step-id="stepId"
        class="photo-item"
        @remove-self="removeUnused(photo)"
        @insert-at="
          insertUnused({
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
.wrapper {
  width: 20%;
  height: 100%;

  position: sticky;
  right: 0;
  top: 5rem;
  margin-top: 5rem;
  margin-bottom: 10rem;

  border-radius: 10px;
  background: var(--q-dark-page);
  box-shadow: 0 -5px 15px rgba(0, 0, 0, 0.2);

  display: flex;
  flex-direction: column;
}

.header {
  padding: 1rem;
  text-align: center;
  font-weight: bold;
  font-size: 1.25rem;
  color: #9ca3af;
}

.container {
  padding: 1rem 0;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;

  .photo-item {
    width: 90%;
    height: auto;
  }
}

@media print {
  .wrapper {
    display: none !important;
  }
}
</style>
