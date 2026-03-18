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
  <div class="unused-sidebar">
    <div class="sidebar-header row no-wrap items-center text-overline text-weight-semibold text-muted">
      <q-icon :name="matPhotoLibrary" size="1rem" />
      <span>Unused</span>
    </div>
    <VueDraggable
      v-model="localUnused"
      class="sidebar-track column no-wrap"
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
    <div v-if="localUnused.length === 0" class="sidebar-empty text-caption text-faint text-center">
      Drop photos here
    </div>
  </div>
</template>

<style lang="scss" scoped>
.unused-sidebar {
  position: sticky;
  top: 4.5rem;
  width: 10rem;
  min-height: 6rem;
  background: var(--surface);
  border: 1px solid color-mix(in srgb, var(--text) 15%, transparent);
  border-radius: var(--radius-md);
  padding: 0.5rem;
}

.sidebar-header {
  gap: var(--gap-sm);
  margin-bottom: var(--gap-md);
}

.sidebar-empty {
  padding: 0.5rem 0;
}

.sidebar-track {
  gap: var(--gap-md);
  max-height: 60vh;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 4px;
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
    width: 100%;
    aspect-ratio: 4 / 3;
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
  .unused-sidebar {
    display: none !important;
  }
}
</style>
