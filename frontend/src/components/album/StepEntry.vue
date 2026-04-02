<script lang="ts" setup>
import type { Step } from "@/client";
import StepMainPage from "./step/StepMainPage.vue";
import StepPhotoPage from "./step/StepPhotoPage.vue";
import StepTextPage from "./step/StepTextPage.vue";
import { useStepLayout } from "@/composables/useStepLayout";
import { usePhotoFocus, STEP_ID_KEY } from "@/composables/usePhotoFocus";
import { useTextMeasure } from "@/composables/useTextMeasure";
import { filterCoverFromPages } from "./albumSections";
import { useI18n } from "vue-i18n";
import { computed, onUnmounted, provide, ref, toRef } from "vue";
import { matAddPhotoAlternate } from "@quasar/extras/material-icons";

const { t } = useI18n();

const props = defineProps<{
  step: Step;
}>();

const dropZoneRef = ref<HTMLElement | null>(null);
const coverDropRef = ref<HTMLElement | null>(null);

const { printMode, isDragging, saveField, onPageUpdate, onUnusedUpdate, onCoverUpdate } =
  useStepLayout(toRef(props, "step"), { dropZoneRef, coverDropRef });

provide(STEP_ID_KEY, props.step.id);

if (!printMode) {
  const photoFocus = usePhotoFocus();
  photoFocus.register(props.step.id, {
    step: toRef(props, "step"),
    onCoverUpdate,
    onUnusedUpdate,
  });
  onUnmounted(() => photoFocus.unregister(props.step.id));
}

const desc = useTextMeasure(computed(() => props.step.description ?? ""));

const photoPages = computed(() =>
  filterCoverFromPages(props.step.pages, props.step.cover, desc.value.type === "short"),
);

// Steps with 0-1 photos have nothing to drag into a new page, so the drop zone is hidden.
const totalPhotos = computed(() =>
  props.step.pages.reduce((n, p) => n + p.length, 0) + props.step.unused.length,
);
</script>

<template>
  <div class="step-entry">
    <div class="step-pages column no-wrap items-center">
      <div class="cover-drop-wrapper relative-position">
        <StepMainPage
          :step="step"
          :description-type="desc.type"
          :main-lines="desc.mainLines"
          @update:name="saveField({ name: $event })"
          @update:description="saveField({ description: $event })"
        />
        <div v-if="!printMode" ref="coverDropRef" class="cover-drop-overlay" :class="{ 'drag-active': isDragging }" />
      </div>

      <StepTextPage
        v-for="(pageLines, i) in desc.continuationLines"
        :key="`text-${i}`"
        :lines="pageLines"
        :description="step.description ?? ''"
        @update:description="saveField({ description: $event })"
      />

      <StepPhotoPage
        v-for="{ originalIdx, page } in photoPages"
        :key="`page-${originalIdx}`"
        :page="page"
        @update:page="onPageUpdate(originalIdx, $event)"
      />

      <div v-if="!printMode && totalPhotos >= 2" class="add-zone relative-position">
        <div class="add-zone-content column no-wrap items-center justify-center text-weight-medium text-muted">
          <q-icon :name="matAddPhotoAlternate" size="1.5rem" />
          <span>{{ t("album.dropPhotoToAdd") }}</span>
        </div>
        <div ref="dropZoneRef" class="drop-overlay absolute-full overflow-hidden" />
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
  margin: var(--gap-md) auto 0;
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

@media (prefers-reduced-motion: reduce) {
  .add-zone-content {
    transition: none;
  }
}
</style>
