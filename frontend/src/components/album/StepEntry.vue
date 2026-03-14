<script lang="ts" setup>
import type { Step, StepUpdate } from "@/client";
import StepMainPage from "./step/StepMainPage.vue";
import StepPhotoPage from "./step/StepPhotoPage.vue";
import StepTextPage from "./step/StepTextPage.vue";
import UnusedSidebar from "./step/UnusedSidebar.vue";
import { usePageDescription } from "@/composables/usePageDescription";
import { useStepMutation } from "@/queries/useStepMutation";
import { computed, ref } from "vue";
import { useDraggable } from "vue-draggable-plus";
import { matAddPhotoAlternate } from "@quasar/extras/material-icons";

const props = defineProps<{
  step: Step;
  printMode?: boolean;
}>();

const descRef = computed(() => props.step.description);
const desc = usePageDescription(descRef);

const stepMutation = useStepMutation();

// Drop zone — useDraggable attaches SortableJS directly to the DOM element,
// avoiding the v-model sync issues that VueDraggable has with static children.
const dropZoneRef = ref<HTMLElement | null>(null);
const dropZoneList = ref<string[]>([]);

function saveLayout(patch: Partial<StepUpdate>) {
  const layout: StepUpdate = {
    cover: props.step.cover,
    pages: props.step.pages,
    unused: props.step.unused,
    ...patch,
  };
  stepMutation.mutate({ sid: props.step.idx, layout });
}

function onCoverUpdate(cover: string) {
  saveLayout({ cover });
}

/** Remove a set of photos from all pages and unused list atomically. */
function withoutPhotos(photoSet: Set<string>) {
  return {
    pages: props.step.pages
      .map((page) => page.filter((p) => !photoSet.has(p)))
      .filter((page) => page.length > 0),
    unused: props.step.unused.filter((p) => !photoSet.has(p)),
  };
}

function onPageUpdate(idx: number, page: string[]) {
  // Find photos that are new to this page (dragged in from elsewhere)
  const existing = new Set(props.step.pages[idx]);
  const added = page.filter((p) => !existing.has(p));

  if (added.length > 0) {
    // Cross-list move: replace target page in-place, strip dragged photos
    // from all other pages atomically (can't use withoutPhotos + splice
    // because filtering empty pages shifts indices).
    const addedSet = new Set(added);
    const pages = props.step.pages
      .map((p, i) =>
        i === idx ? page : p.filter((photo) => !addedSet.has(photo)),
      )
      .filter((p) => p.length > 0);
    const unused = props.step.unused.filter((p) => !addedSet.has(p));
    saveLayout({ pages, unused });
  } else {
    // Same-list reorder
    const pages = [...props.step.pages];
    pages[idx] = page;
    saveLayout({ pages });
  }
}

function onUnusedUpdate(unused: string[]) {
  // Find photos that are new to the unused list (dragged in from a page)
  const existing = new Set(props.step.unused);
  const added = unused.filter((p) => !existing.has(p));

  if (added.length > 0) {
    // Cross-list move: atomically remove from source pages
    const cleaned = withoutPhotos(new Set(added));
    saveLayout({ ...cleaned, unused });
  } else {
    saveLayout({ unused });
  }
}

function addPage() {
  saveLayout({ pages: [...props.step.pages, []] });
}

useDraggable(dropZoneRef, dropZoneList, {
  group: "photos",
  animation: 200,
  onAdd: () => {
    if (dropZoneList.value.length === 0) return;
    const photos = [...dropZoneList.value];
    dropZoneList.value = [];
    const cleaned = withoutPhotos(new Set(photos));
    saveLayout({ ...cleaned, pages: [...cleaned.pages, photos] });
  },
});
</script>

<template>
  <div class="step-entry">
    <StepMainPage
      :step="step"
      :description-type="desc.type"
      :main-page-text="desc.mainPageText"
      @update:cover="onCoverUpdate"
    />

    <StepTextPage
      v-for="(text, i) in desc.continuationTexts"
      :key="`text-${i}`"
      :text="text"
      :step-name="step.name"
      :location-name="step.location.name"
    />

    <StepPhotoPage
      v-for="(page, idx) in step.pages"
      :key="`page-${idx}`"
      :page="page"
      :step-id="step.idx"
      :orientations="step.orientations ?? {}"
      @update:page="onPageUpdate(idx, $event)"
    />

    <!-- Add page drop zone (editor only) -->
    <div v-if="!printMode" class="add-zone" @click="addPage">
      <div class="add-zone-content">
        <q-icon :name="matAddPhotoAlternate" size="1.5rem" />
        <span class="add-label">Add Photo Page</span>
        <span class="add-hint">or drop a photo here</span>
      </div>
      <div ref="dropZoneRef" class="drop-overlay" />
    </div>

    <!-- Unused photos tray (editor only) -->
    <UnusedSidebar
      v-if="!printMode"
      :assets="step.unused"
      :step-id="step.idx"
      @update:unused-photos="onUnusedUpdate"
    />
  </div>
</template>

<style lang="scss" scoped>
.step-entry {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.add-zone {
  position: relative;
  width: calc(297mm * var(--editor-zoom));
  margin: 0.5rem auto;
  min-height: 3.5rem;
}

.drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  overflow: hidden;

  // Hide dropped items — they get processed immediately
  :deep(*) {
    opacity: 0;
    width: 0;
    height: 0;
  }
}

.add-zone-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  width: 100%;
  padding: 1rem;
  border: 2px dashed color-mix(in srgb, var(--text) 20%, transparent);
  border-radius: 0.75rem;
  color: var(--text-muted);
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition:
    border-color 0.15s,
    color 0.15s,
    background 0.15s;

  &:hover {
    border-color: var(--q-primary);
    color: var(--q-primary);
  }
}

// When SortableJS is dragging over, the overlay gets a ghost element
.add-zone:has(.sortable-ghost) .add-zone-content {
  border-color: var(--q-primary);
  background: color-mix(in srgb, var(--q-primary) 8%, transparent);
  color: var(--q-primary);
}

.add-label {
  font-size: 0.9rem;
}

.add-hint {
  font-size: 0.7rem;
  font-weight: 400;
  opacity: 0.6;
}

@media print {
  :deep(.page-container) {
    width: 297mm !important;
    height: 210mm !important;
    max-width: 297mm !important;
    max-height: 210mm !important;
    overflow: hidden !important;
    box-sizing: border-box !important;
    page-break-after: always;
    page-break-inside: avoid;
    flex-shrink: 0;
  }

  .add-zone {
    display: none !important;
  }
}
</style>
