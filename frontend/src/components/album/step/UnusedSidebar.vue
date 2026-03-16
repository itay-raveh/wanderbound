<script lang="ts" setup>
import { VueDraggable } from "vue-draggable-plus";
import MediaItem from "../MediaItem.vue";
import { matPhotoLibrary } from "@quasar/extras/material-icons";
import { useLocalCopy } from "@/composables/useLocalCopy";

const props = defineProps<{
  assets: Array<string>;
  stepId: number;
}>();

const emit = defineEmits<{
  "update:unused-photos": [unused: string[]];
}>();

const localUnused = useLocalCopy(() => props.assets);

function emitUnused() {
  emit("update:unused-photos", [...localUnused.value]);
}
</script>

<template>
  <div class="unused-tray">
    <div class="tray-header row no-wrap items-center text-overline text-weight-semibold text-muted">
      <q-icon :name="matPhotoLibrary" size="1rem" />
      <span>{{ localUnused.length }} unused photo{{ localUnused.length !== 1 ? 's' : '' }}</span>
    </div>
    <VueDraggable
      v-model="localUnused"
      class="tray-track row no-wrap"
      group="photos"
      :animation="200"
      @update="emitUnused"
      @add="emitUnused"
    >
      <MediaItem
        v-for="photo in localUnused"
        :key="photo"
        :media="photo"
        :step-id="stepId"
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
  max-width: calc(var(--page-width) * var(--editor-zoom));
  background: var(--surface);
  border: 1px solid color-mix(in srgb, var(--text) 15%, transparent);
  border-radius: var(--radius-md);
  padding: 0.5rem 0.75rem;
  margin: 1rem 0 1.5rem;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.15);
}

.tray-header {
  gap: var(--gap-md);
  margin-bottom: var(--gap-md);
}

.tray-track {
  gap: var(--gap-md);
  overflow-x: auto;
  padding: 0.25rem 0;
  min-height: 4.5rem;

  &::-webkit-scrollbar {
    height: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: var(--radius-xs);
  }

  // Hide video play overlay — videos are just static thumbnails in the tray.
  :deep(.play-overlay) {
    display: none;
  }

  // Constrain ALL children — including SortableJS ghost clones dragged
  // in from photo pages, which would otherwise retain their large page size.
  > :deep(*) {
    width: 6rem;
    height: 4.5rem;
    flex-shrink: 0;
    border-radius: var(--radius-xs);
    overflow: hidden;
    cursor: grab;

    &:active {
      cursor: grabbing;
    }
  }
}

@media print {
  .unused-tray {
    display: none !important;
  }
}
</style>
