<script lang="ts" setup>
import type { Step, StepLayout } from "@/client";
import StepMainPage from "./step/StepMainPage.vue";
import StepPhotoPage from "./step/StepPhotoPage.vue";
import StepTextPage from "./step/StepTextPage.vue";
import UnusedSidebar from "./step/UnusedSidebar.vue";
import { usePageDescription } from "@/composables/usePageDescription";
import { useStepMutation } from "@/queries/useStepMutation";
import { computed } from "vue";

const props = defineProps<{
  albumId: string;
  colors: Record<string, string>;
  step: Step;
  stepsRanges: string;
  printMode?: boolean;
}>();

const descRef = computed(() => props.step.description);
const desc = usePageDescription(descRef);

const stepMutation = useStepMutation(
  () => props.albumId,
  () => props.stepsRanges,
);

function saveLayout(patch: Partial<StepLayout>) {
  const layout: StepLayout = {
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
</script>

<template>
  <div class="step">
    <div class="pages">
      <StepMainPage
        :colors="colors"
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
        :album-id="albumId"
        :page="page"
        :step-id="step.idx"
        @update:page="onPageUpdate(idx, $event)"
      />

      <div v-if="!printMode" class="add-container">
        <button class="add-btn" title="Add Photo Page" @click="addPage">
          +
        </button>
      </div>
    </div>

    <UnusedSidebar
      v-if="!printMode"
      :album-name="albumId"
      :assets="step.unused"
      :step-id="step.idx"
      @update:unused-photos="onUnusedUpdate"
    />
  </div>
</template>

<style lang="scss" scoped>
.step {
  display: flex;
}

.pages {
  display: flex;
  flex-direction: column;
}

.add-container {
  display: flex;
  justify-content: center;
  padding: 20px 0;
  width: 100%;
  max-width: 297mm;
  margin: 0 auto;
}

.add-btn {
  background-color: var(--q-primary);
  color: white;
  border: none;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  font-size: 24px;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    transform 0.2s,
    background-color 0.2s;
}

.add-btn:hover {
  transform: scale(1.1);
  background-color: var(--q-primary);
  filter: brightness(0.9);
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
  .add-container {
    display: none !important;
  }
}
</style>
