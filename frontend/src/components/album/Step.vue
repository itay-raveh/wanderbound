<script lang="ts" setup>
import { type Album, type Step } from "@/api";
import StepMainPage from "./step/StepMainPage.vue";
import StepPhotoPage from "./step/StepPhotoPage.vue";
import UnusedSidebar from "./step/UnusedSidebar.vue";

defineProps<{
  album: Album;
  step: Step;
}>();

const emit = defineEmits<{
  "update:cover": [path: string];
}>();
</script>

<template>
  <div class="step">
    <div class="pages">
      <StepMainPage
        :album="album"
        :step="step"
        @update:cover="
          (path) => {
            emit('update:cover', path);
          }
        "
      />

      <StepPhotoPage
        v-for="(page, idx) in step.pages"
        :key="`page-${idx}`"
        :album-name="album.id"
        :page="page"
        :step-id="step.idx"
        @update:page="step.pages[idx] = $event"
      />

      <div class="add-container">
        <button
          class="add-btn"
          title="Add Photo Page"
          @click="step.pages.push([])"
        >
          +
        </button>
      </div>
    </div>

    <UnusedSidebar
      :album-name="album.id"
      :assets="step.unused"
      :step-id="step.idx"
      @update:unused-photos="step.unused = $event"
    />
  </div>
</template>

<style lang="scss" scoped>
.step {
  display: flex;
  // justify-content: flex-start;
  // align-items: flex-start;
  // width: 100%;
  // height: 100%;
}

.pages {
  display: flex;
  flex-direction: column;
  // flex-grow: 1;
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
