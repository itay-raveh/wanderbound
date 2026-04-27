<script lang="ts" setup>
import type { Step } from "@/client";
import { useDraggable } from "vue-draggable-plus";
import MediaItem from "../album/MediaItem.vue";
import { matPhotoLibrary } from "@quasar/extras/material-icons";
import { unusedUpdatePayload } from "@/composables/useStepLayout";
import { useStepMutation } from "@/queries/useStepMutation";
import { useI18n } from "vue-i18n";
import { ref, watch } from "vue";

const { t } = useI18n();

const props = defineProps<{
  step: Step;
  albumId: string;
}>();

const stepMut = useStepMutation(() => props.albumId);

/** Local copy for instant drag feedback. Syncs from prop on external changes. */
const localUnused = ref([...props.step.unused]);
watch(
  () => props.step.unused,
  (val) => {
    if (
      val.length === localUnused.value.length &&
      val.every((v, i) => v === localUnused.value[i])
    )
      return;
    localUnused.value = [...val];
  },
);

function save() {
  stepMut.mutate({
    sid: props.step.id,
    update: unusedUpdatePayload(props.step, [...localUnused.value]),
  });
}

const trackRef = ref<HTMLElement | null>(null);

useDraggable(trackRef, localUnused, {
  group: "photos",
  animation: 200,
  draggable: ".media-item",
  onUpdate() {
    save();
  },
  onAdd() {
    save();
  },
});
</script>

<template>
  <div class="unused-drawer">
    <div
      class="drawer-header row no-wrap items-center text-overline text-weight-semibold text-muted"
    >
      <q-icon :name="matPhotoLibrary" size="var(--type-md)" />
      <span>{{ t("album.unused") }}</span>
      <span class="text-faint">{{ localUnused.length }}</span>
      <q-tooltip>{{ t("album.unusedHint") }}</q-tooltip>
    </div>
    <div ref="trackRef" class="drawer-track column no-wrap">
      <MediaItem v-for="photo in localUnused" :key="photo" :media="photo" />
      <div v-if="localUnused.length === 0" class="drawer-empty">
        {{ t("album.dropPhotosHere") }}
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.unused-drawer {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: var(--gap-md);
}

.drawer-header {
  gap: var(--gap-sm);
  margin-bottom: var(--gap-md);
  flex-shrink: 0;
}

.drawer-empty {
  grid-column: 1 / -1;
  min-height: 8rem;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--gap-md-lg) var(--gap-sm);
  border: 0.125rem dashed color-mix(in srgb, var(--text) 18%, transparent);
  border-radius: var(--radius-sm);
  font-size: var(--type-xs);
  color: var(--text-faint);
  text-align: center;
  transition:
    border-color var(--duration-fast),
    color var(--duration-fast);
}

// Highlight empty state when dragging over
.unused-drawer:has(.sortable-ghost) .drawer-empty {
  border-color: color-mix(in srgb, var(--q-primary) 50%, transparent);
  color: var(--q-primary);
}

.drawer-track {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--gap-sm);
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border-color) transparent;

  &::-webkit-scrollbar {
    width: 0.25rem;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: var(--radius-xs);
  }

  // Hide video play overlay - just static thumbnails in the tray.
  :deep(.play-overlay) {
    display: none;
  }

  // Constrain ALL children - including SortableJS ghost clones dragged
  // in from photo pages, which would otherwise retain their large page size.
  > :deep(*) {
    width: 100%;
    aspect-ratio: 4 / 3;
    border-radius: var(--radius-xs);
    overflow: hidden;
    cursor: grab;

    &:active {
      cursor: grabbing;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .drawer-empty {
    transition: none;
  }
}
</style>
