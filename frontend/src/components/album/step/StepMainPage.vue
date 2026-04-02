<script lang="ts" setup>
import type { Step } from "@/client";
import type { DescriptionType, JustifiedLine } from "@/composables/useTextMeasure";
import { useI18n } from "vue-i18n";
import { symOutlinedImage } from "@quasar/extras/material-symbols-outlined";
import EditableText from "../EditableText.vue";
import { computed } from "vue";
import MediaItem from "../MediaItem.vue";
import StepMetaPanel from "./StepMetaPanel.vue";

const { t } = useI18n();

const props = defineProps<{
  step: Step;
  descriptionType: DescriptionType;
  mainLines?: JustifiedLine[] | null;
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
      :lines="mainLines"
      :compact="isLongDesc"
      class="meta-side"
      @update:name="emit('update:name', $event)"
      @update:description="emit('update:description', $event)"
    />

    <div class="content-panel">
      <EditableText
        v-if="isLongDesc && step.description"
        :model-value="step.description ?? ''"
        multiline
        dir="auto"
        class="text-body-columns description-full"
        :lines="mainLines"
        @update:model-value="emit('update:description', $event)"
      />
      <template v-else>
        <MediaItem
          v-if="step.cover"
          :media="step.cover"
          fit-cover
          :focusable="false"
          class="cover-media"
        />
        <div v-else class="cover-placeholder">
          <q-icon :name="symOutlinedImage" class="placeholder-icon" />
          <span class="placeholder-text">{{ t("album.dropStepCover") }}</span>
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
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--gap-md);
  background: color-mix(in srgb, var(--border-color) 30%, var(--page-bg, var(--bg)));
  border: 0.125rem dashed color-mix(in srgb, var(--text) 15%, transparent);
  margin: var(--gap-md-lg);
}

.placeholder-icon {
  font-size: var(--display-2);
  color: var(--text-faint);
}

.placeholder-text {
  font-size: var(--type-sm);
  font-weight: 500;
  color: var(--text-faint);
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
