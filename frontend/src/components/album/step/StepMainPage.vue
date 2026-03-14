<script lang="ts" setup>
import type { Step } from "@/client";
import type { DescriptionType } from "@/composables/usePageDescription";
import { useAlbum } from "@/composables/useAlbum";
import { usePrintMode } from "@/composables/usePrintReady";
import { mediaUrl, mediaSrcset, SIZES_HALF } from "@/utils/media";
import { chooseTextDir } from "@/utils/text";
import { computed } from "vue";
import StepMetaPanel from "./StepMetaPanel.vue";

const { albumId } = useAlbum();

const props = defineProps<{
  step: Step;
  descriptionType: DescriptionType;
  mainPageText: string;
}>();

defineEmits<{
  "update:cover": [path: string];
}>();

const isLongDesc = computed(
  () =>
    props.descriptionType === "long" ||
    props.descriptionType === "extra-long",
);

const printMode = usePrintMode();
const imgLoading = computed(() => (printMode ? "eager" : "lazy"));
</script>

<template>
  <div :class="{ 'long-desc': isLongDesc }" class="page-container step-main">
    <StepMetaPanel
      :step="step"
      :description-type="descriptionType"
      :main-page-text="mainPageText"
      :compact="isLongDesc"
      class="meta-side"
    />

    <div class="content-panel">
      <div
        v-if="isLongDesc && mainPageText"
        :dir="chooseTextDir(mainPageText)"
        class="description-full"
      >
        {{ mainPageText }}
      </div>
      <q-img
        v-else-if="step.cover"
        :src="mediaUrl(step.cover, albumId)"
        :srcset="printMode ? undefined : mediaSrcset(step.cover, albumId)"
        :sizes="printMode ? undefined : SIZES_HALF"
        :loading="imgLoading"
        class="cover-photo"
      />
      <div v-else class="cover-placeholder">
        <span>Drop Step Cover</span>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.step-main {
  display: flex;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
}

.meta-side {
  flex: 0 0 42%;
}

.content-panel {
  flex: 1;
  display: flex;
  min-height: 0;
}

.cover-photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  color: var(--text-faint);
  font-size: 0.85rem;
}

.description-full {
  padding: 2.5rem 3rem;
  font-size: 0.9rem;
  line-height: 1.65;
  color: var(--text);
  white-space: pre-wrap;
  text-align: justify;
  column-count: 2;
  column-gap: 2.5rem;
  overflow: hidden;
  width: 100%;
  box-sizing: border-box;
}

// ─── Long Description Layout ───
.step-main.long-desc {
  flex-direction: column;

  .meta-side {
    flex: 0 0 auto;
  }

  .content-panel {
    flex: 1;
    min-height: 0;
  }
}
</style>
