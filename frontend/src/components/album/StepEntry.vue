<script lang="ts" setup>
import type { Step, StepUpdate } from "@/client";
import StepMainPage from "./step/StepMainPage.vue";
import StepPhotoPage from "./step/StepPhotoPage.vue";
import StepTextPage from "./step/StepTextPage.vue";
import UnusedSidebar from "./step/UnusedSidebar.vue";
import { useDragState } from "@/composables/useDragState";
import { filterCoverFromPages, useTextMeasure } from "@/composables/useTextMeasure";
import { usePrintMode } from "@/composables/usePrintReady";
import { useStepMutation } from "@/queries/useStepMutation";
import { computed, ref } from "vue";
import { useDraggable } from "vue-draggable-plus";
import { matAddPhotoAlternate } from "@quasar/extras/material-icons";

const props = defineProps<{
  step: Step;
}>();

const printMode = usePrintMode();
const isDragging = useDragState();

const desc = useTextMeasure(computed(() => props.step.description ?? ""));

const photoPages = computed(() =>
  filterCoverFromPages(props.step.pages, props.step.cover, desc.value.type === "short"),
);

const stepMutation = useStepMutation();

// Drop zones — useDraggable attaches SortableJS directly to the DOM element,
// avoiding the v-model sync issues that VueDraggable has with static children.
const dropZoneRef = ref<HTMLElement | null>(null);
const dropZoneList = ref<string[]>([]);
const coverDropRef = ref<HTMLElement | null>(null);
const coverDropList = ref<string[]>([]);

function saveField(patch: Partial<StepUpdate>) {
  stepMutation.mutate({ sid: props.step.idx, update: patch });
}

function saveLayout(patch: Partial<StepUpdate>) {
  const update: StepUpdate = {
    cover: props.step.cover,
    pages: props.step.pages,
    unused: props.step.unused,
    ...patch,
  };
  stepMutation.mutate({ sid: props.step.idx, update });
}

function onCoverUpdate(cover: string) {
  const oldCover = props.step.cover;
  const { pages, unused } = withoutPhotos(new Set([cover]));
  saveLayout({
    cover,
    pages,
    unused: oldCover ? [...unused, oldCover] : unused,
  });
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

if (!printMode) {
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

  useDraggable(coverDropRef, coverDropList, {
    group: "photos",
    animation: 200,
    onAdd: () => {
      if (coverDropList.value.length === 0) return;
      const photo = coverDropList.value[0]!;
      coverDropList.value = [];
      onCoverUpdate(photo);
    },
  });
}
</script>

<template>
  <div class="step-entry">
    <div class="step-pages column no-wrap items-center">
      <div class="cover-drop-wrapper relative-position">
        <StepMainPage
          :step="step"
          :description-type="desc.type"
          :main-page-text="desc.mainPageText"
          @update:name="saveField({ name: $event })"
          @update:description="saveField({ description: $event })"
        />
        <div v-if="!printMode" ref="coverDropRef" class="cover-drop-overlay" :class="{ 'drag-active': isDragging }" />
      </div>

      <StepTextPage
        v-for="(text, i) in desc.continuationTexts"
        :key="`text-${i}`"
        :text="text"
        :description="step.description ?? ''"
        @update:description="saveField({ description: $event })"
      />

      <StepPhotoPage
        v-for="{ originalIdx, page } in photoPages"
        :key="`page-${originalIdx}`"
        :page="page"
        :step-id="step.idx"
        @update:page="onPageUpdate(originalIdx, $event)"
      />

      <!-- Add page drop zone (editor only) -->
      <div v-if="!printMode" class="add-zone relative-position">
        <div class="add-zone-content column no-wrap items-center justify-center text-weight-medium text-muted">
          <q-icon :name="matAddPhotoAlternate" size="1.5rem" />
          <span>Drop photo to add page</span>
        </div>
        <div ref="dropZoneRef" class="drop-overlay absolute-full overflow-hidden" />
      </div>
    </div>

    <!-- Unused photos sidebar (editor only) -->
    <div v-if="!printMode" class="sidebar-anchor">
      <UnusedSidebar
        :assets="step.unused"
        :step-id="step.idx"
        @update:unused-photos="onUnusedUpdate"
      />
    </div>

  </div>
</template>

<style lang="scss" scoped>
.step-entry {
  --meta-width: calc(var(--meta-ratio) * 100%);
  position: relative;
}

.sidebar-anchor {
  position: absolute;
  right: 0.75rem;
  top: 0;
  bottom: 0;
}

.cover-drop-overlay {
  position: absolute;
  // Cover only the right side (content panel, not meta panel)
  top: 0;
  right: 0;
  bottom: 0;
  left: var(--meta-width);
  z-index: 1;
  overflow: hidden;
  pointer-events: none;

  &.drag-active {
    pointer-events: auto;
  }

  :deep(*) {
    opacity: 0;
    width: 0;
    height: 0;
  }
}

// Highlight cover area when dragging over
.cover-drop-wrapper:has(.cover-drop-overlay .sortable-ghost) .cover-drop-overlay {
  &::after {
    content: "";
    position: absolute;
    inset: 0;
    border: 2px solid var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
    pointer-events: none;
  }
}

.add-zone {
  width: calc(var(--page-width) * var(--editor-zoom));
  margin: 0.5rem auto 3rem;
  min-height: 3.5rem;
}

.drop-overlay {
  z-index: 1;

  // Hide dropped items — they get processed immediately
  :deep(*) {
    opacity: 0;
    width: 0;
    height: 0;
  }
}

.add-zone-content {
  gap: var(--gap-sm);
  width: 100%;
  padding: 1rem;
  border: 2px dashed color-mix(in srgb, var(--text) 20%, transparent);
  border-radius: var(--radius-lg);
  font-size: var(--type-sm);
  transition:
    border-color var(--duration-fast),
    color var(--duration-fast),
    background var(--duration-fast);

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

@media print {
  :deep(.page-container) {
    width: var(--page-width) !important;
    height: var(--page-height) !important;
    max-width: var(--page-width) !important;
    max-height: var(--page-height) !important;
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
