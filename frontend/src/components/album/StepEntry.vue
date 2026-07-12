<script lang="ts" setup>
import type { StepRead as Step } from "@/client";
import StepMainPage from "./step/StepMainPage.vue";
import StepPhotoPage from "./step/StepPhotoPage.vue";
import StepDescriptionPage from "./step/StepDescriptionPage.vue";
import { useStepLayout } from "@/composables/useStepLayout";
import { STEP_ID_KEY } from "@/composables/usePhotoFocus";
import { useTextLayout } from "@/composables/useTextLayout";
import { useAlbum } from "@/composables/useAlbum";
import { planStepPages } from "./stepPages";
import { useI18n } from "vue-i18n";
import { computed, provide, ref, toRef } from "vue";
import { matAddPhotoAlternate } from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = defineProps<{
  step: Step;
  pageIndex?: number;
  addZoneOnly?: boolean;
}>();

const dropZoneRef = ref<HTMLElement | null>(null);
const coverDropRef = ref<HTMLElement | null>(null);

const { printMode, isDragging, saveField, onPageUpdate } = useStepLayout(
  toRef(props, "step"),
  { dropZoneRef, coverDropRef },
);

provide(STEP_ID_KEY, props.step.id);

const desc = useTextLayout(computed(() => props.step.description ?? ""));
const { mediaByName } = useAlbum();
const stepPagePlan = computed(() =>
  planStepPages(props.step, mediaByName.value, desc.value.pages),
);
const continuationPages = computed(() => stepPagePlan.value.continuationPages);
const continuationPhotos = computed(() => stepPagePlan.value.continuationPhotos);
const photoPages = computed(() => stepPagePlan.value.photoPages);

const selectedDescriptionPage = computed(() => {
  if (props.pageIndex == null) return null;
  const index = props.pageIndex - 1;
  return index >= 0 && index < continuationPages.value.length
    ? { lines: continuationPages.value[index], index }
    : null;
});

const selectedPhotoPage = computed(() => {
  if (props.pageIndex == null) return null;
  const index = props.pageIndex - 1 - continuationPages.value.length;
  return index >= 0 && index < photoPages.value.length
    ? { ...photoPages.value[index], index }
    : null;
});

const hasPhotoDropZone = computed(
  () => stepPagePlan.value.hasPhotoDropZone,
);
</script>

<template>
  <div class="step-entry">
    <div v-if="addZoneOnly" class="step-pages column no-wrap items-center">
      <div
        v-if="!printMode && hasPhotoDropZone"
        class="add-zone relative-position"
      >
        <div
          class="add-zone-content column no-wrap items-center justify-center text-weight-medium text-muted"
        >
          <q-icon :name="matAddPhotoAlternate" size="1.5rem" />
          <span>{{ t("album.dropPhotoToAdd") }}</span>
        </div>
        <div
          ref="dropZoneRef"
          class="drop-overlay absolute-full overflow-hidden"
        />
      </div>
    </div>

    <div v-else class="step-pages column no-wrap items-center">
      <div
        v-if="pageIndex == null || pageIndex === 0"
        class="cover-drop-wrapper relative-position"
      >
        <StepMainPage
          :step="step"
          :sidebar-lines="stepPagePlan.sidebarLines"
          @update:name="saveField({ name: $event })"
          @update:description="saveField({ description: $event })"
        />
        <div
          v-if="!printMode"
          ref="coverDropRef"
          class="cover-drop-overlay"
          :class="{ 'drag-active': isDragging }"
        />
      </div>

      <StepDescriptionPage
        v-if="selectedDescriptionPage"
        :lines="selectedDescriptionPage.lines"
        :description="step.description ?? ''"
        :photo="continuationPhotos[selectedDescriptionPage.index] ?? null"
        @update:description="saveField({ description: $event })"
      />
      <StepDescriptionPage
        v-else-if="pageIndex == null"
        v-for="(pageLines, i) in continuationPages"
        :key="`desc-${i}`"
        :lines="pageLines"
        :description="step.description ?? ''"
        :photo="continuationPhotos[i] ?? null"
        @update:description="saveField({ description: $event })"
      />

      <StepPhotoPage
        v-if="selectedPhotoPage"
        :page="selectedPhotoPage.page"
        @update:page="onPageUpdate(selectedPhotoPage.originalIdx, $event)"
      />
      <StepPhotoPage
        v-else-if="pageIndex == null"
        v-for="{ originalIdx, page } in photoPages"
        :key="`page-${originalIdx}`"
        :page="page"
        @update:page="onPageUpdate(originalIdx, $event)"
      />

      <div
        v-if="pageIndex == null && !printMode && hasPhotoDropZone"
        class="add-zone relative-position"
      >
        <div
          class="add-zone-content column no-wrap items-center justify-center text-weight-medium text-muted"
        >
          <q-icon :name="matAddPhotoAlternate" size="1.5rem" />
          <span>{{ t("album.dropPhotoToAdd") }}</span>
        </div>
        <div
          ref="dropZoneRef"
          class="drop-overlay absolute-full overflow-hidden"
        />
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.step-entry {
  --meta-width: calc(var(--meta-ratio) * 100%);
  position: relative;
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
.cover-drop-wrapper:has(.cover-drop-overlay .sortable-ghost)
  .cover-drop-overlay {
  &::after {
    content: "";
    position: absolute;
    inset: 0;
    border: 0.125rem solid var(--q-primary);
    background: color-mix(in srgb, var(--q-primary) 10%, transparent);
    pointer-events: none;
  }
}

.add-zone {
  width: calc(var(--page-width) * var(--editor-zoom));
  margin: var(--gap-md) auto var(--gap-lg);
  min-height: 3.5rem;
}

.drop-overlay {
  z-index: 1;

  // Hide dropped items - they get processed immediately
  :deep(*) {
    opacity: 0;
    width: 0;
    height: 0;
  }
}

.add-zone-content {
  gap: var(--gap-sm);
  width: 100%;
  padding: var(--gap-lg);
  border: 0.125rem dashed color-mix(in srgb, var(--text) 20%, transparent);
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

@media (prefers-reduced-motion: reduce) {
  .add-zone-content {
    transition: none;
  }
}
</style>
