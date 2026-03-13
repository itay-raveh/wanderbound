<script lang="ts" setup>
import type { Step, StepUpdate } from "@/client";
import StepMainPage from "./step/StepMainPage.vue";
import StepPhotoPage from "./step/StepPhotoPage.vue";
import StepTextPage from "./step/StepTextPage.vue";
import UnusedSidebar from "./step/UnusedSidebar.vue";
import { usePageDescription } from "@/composables/usePageDescription";
import { useStepMutation } from "@/queries/useStepMutation";
import { computed, ref } from "vue";
import { VueDraggable } from "vue-draggable-plus";
import { matAddPhotoAlternate } from "@quasar/extras/material-icons";

const props = defineProps<{
  colors: Record<string, string>;
  step: Step;
  tripStart: string;
  printMode?: boolean;
}>();

const descRef = computed(() => props.step.description);
const desc = usePageDescription(descRef);

const stepMutation = useStepMutation();

// Temporary list for the drop zone — when a photo lands here, create a new page
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

function onPageUpdate(idx: number, page: string[]) {
  const pages = [...props.step.pages];
  pages[idx] = page;
  saveLayout({ pages });
}

function onUnusedUpdate(unused: string[]) {
  saveLayout({ unused });
}

function addPage() {
  saveLayout({ pages: [...props.step.pages, []] });
}

function onDropZoneChange() {
  if (dropZoneList.value.length > 0) {
    // A photo was dropped — create a new page with it
    const photos = [...dropZoneList.value];
    dropZoneList.value = [];
    saveLayout({ pages: [...props.step.pages, photos] });
  }
}
</script>

<template>
  <div class="step-entry">
    <StepMainPage
      :colors="colors"
      :step="step"
      :trip-start="tripStart"
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
    <VueDraggable
      v-if="!printMode"
      v-model="dropZoneList"
      class="add-zone"
      group="photos"
      :animation="200"
      @change="onDropZoneChange"
    >
      <div class="add-zone-content" @click="addPage">
        <q-icon :name="matAddPhotoAlternate" size="1.5rem" />
        <span class="add-label">Add Photo Page</span>
        <span class="add-hint">or drop a photo here</span>
      </div>
    </VueDraggable>

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
  width: calc(297mm * var(--editor-zoom));
  margin: 0.5rem auto;
  min-height: 3.5rem;
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

// When SortableJS is dragging over, the zone gets the sortable-chosen class
.add-zone:has(.sortable-ghost) .add-zone-content,
.add-zone.sortable-drag-over .add-zone-content {
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
