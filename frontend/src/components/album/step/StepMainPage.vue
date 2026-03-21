<script lang="ts" setup>
import type { Step } from "@/client";
import type { DescriptionType } from "@/composables/useTextMeasure";
import { useI18n } from "vue-i18n";
import EditableText from "../EditableText.vue";
import { computed } from "vue";
import MediaItem from "../MediaItem.vue";
import StepMetaPanel from "./StepMetaPanel.vue";

const { t } = useI18n();

const props = defineProps<{
  step: Step;
  descriptionType: DescriptionType;
  mainPageText: string;
}>();

const emit = defineEmits<{
  "update:name": [name: string];
  "update:description": [description: string];
}>();

const isLongDesc = computed(() => props.descriptionType !== "short");
</script>

<template>
  <div :class="{ 'long-desc': isLongDesc }" class="page-container step-main">
    <StepMetaPanel
      :step="step"
      :description-type="descriptionType"
      :main-page-text="mainPageText"
      :compact="isLongDesc"
      class="meta-side"
      @update:name="emit('update:name', $event)"
      @update:description="emit('update:description', $event)"
    />

    <div class="content-panel">
      <EditableText
        v-if="isLongDesc && mainPageText"
        :model-value="step.description ?? ''"
        multiline
        dir="auto"
        class="text-body-columns description-full"
        :display-value="mainPageText"
        @update:model-value="emit('update:description', $event)"
      />
      <template v-else>
        <MediaItem
          v-if="step.cover"
          :media="step.cover"
          cover
          class="cover-media"
        />
        <div v-else class="cover-placeholder fit flex flex-center text-faint">
          <span>{{ t("album.dropStepCover") }}</span>
        </div>
      </template>
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
  flex: 0 0 var(--meta-width);
}

.content-panel {
  flex: 1;
  display: flex;
  min-height: 0;
}

.cover-media {
  cursor: default;

  &:active {
    cursor: default;
  }
}

.cover-placeholder {
  background: var(--bg-secondary);
  font-size: var(--type-sm);
}

.description-full {
  width: 100%;
}

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
