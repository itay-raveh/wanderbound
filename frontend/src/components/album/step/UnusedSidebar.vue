<script lang="ts" setup>
import { ref, watch } from "vue";
import { VueDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";
import { matPhotoLibrary } from "@quasar/extras/material-icons";

const props = defineProps<{
  assets: Array<string>;
  stepId: number;
}>();

const emit = defineEmits<{
  "update:unused-photos": [unused: string[]];
}>();

const localUnused = ref([...props.assets]);

watch(
  () => props.assets,
  (val) => {
    localUnused.value = [...val];
  },
);

function onDragChange() {
  emit("update:unused-photos", [...localUnused.value]);
}
</script>

<template>
  <div class="unused-tray">
    <div class="tray-header">
      <q-icon :name="matPhotoLibrary" size="1rem" />
      <span>{{ localUnused.length }} unused photo{{ localUnused.length !== 1 ? 's' : '' }}</span>
    </div>
    <VueDraggable
      v-model="localUnused"
      class="tray-track"
      group="photos"
      :animation="200"
      @change="onDragChange"
    >
      <MediaItem
        v-for="photo in localUnused"
        :key="photo"
        :media="photo"
        :step-id="stepId"
        class="tray-item"
      />
    </VueDraggable>
  </div>
</template>

<style lang="scss" scoped>
.unused-tray {
  position: sticky;
  bottom: 0;
  z-index: 10;
  width: 100%;
  max-width: calc(297mm * var(--editor-zoom));
  background: var(--surface);
  border: 1px solid color-mix(in srgb, var(--text) 15%, transparent);
  border-radius: 0.5rem;
  padding: 0.5rem 0.75rem;
  margin: 1rem 0 1.5rem;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.15);
}

.tray-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.4rem;
}

.tray-track {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding: 0.25rem 0;
  min-height: 4.5rem;

  &::-webkit-scrollbar {
    height: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: 2px;
  }
}

.tray-item {
  width: 6rem;
  height: 4.5rem;
  flex-shrink: 0;
  border-radius: 0.25rem;
  overflow: hidden;
  cursor: grab;

  &:active {
    cursor: grabbing;
  }
}

@media print {
  .unused-tray {
    display: none !important;
  }
}
</style>
