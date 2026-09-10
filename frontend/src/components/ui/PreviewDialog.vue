<script setup lang="ts">
import { useId } from "vue";
import { useI18n } from "vue-i18n";

const show = defineModel<boolean>({ required: true });
defineProps<{
  title: string;
  previewLabel: string;
  aspectRatio: number;
  closeLabel?: string;
  applyLabel?: string;
  applyDisabled?: boolean;
  applying?: boolean;
  persistent?: boolean;
  controlsBelow?: boolean;
}>();
defineEmits<{ apply: [] }>();
const id = useId();
const { t } = useI18n();
</script>

<template>
  <q-dialog
    v-model="show"
    :aria-labelledby="id"
    :persistent="persistent || applying"
  >
    <q-card class="preview-dialog">
      <q-card-section class="preview-header">
        <h2 :id="id" class="preview-title">{{ title }}</h2>
      </q-card-section>
      <q-card-section
        class="preview-workspace"
        :class="{ 'has-controls': $slots.controls && !controlsBelow }"
      >
        <div class="preview-column">
          <div
            class="preview-viewport"
            :style="{
              aspectRatio: String(aspectRatio),
              maxWidth: `${aspectRatio * 56}vh`,
            }"
            :aria-label="previewLabel"
            role="region"
          >
            <slot />
          </div>
        </div>
        <div v-if="$slots.controls" class="preview-controls">
          <slot name="controls" />
        </div>
      </q-card-section>
      <q-card-actions class="preview-actions" align="right">
        <q-btn
          class="cancel-button"
          flat
          no-caps
          :disable="applying"
          :label="closeLabel ?? t('common.close')"
          @click="show = false"
        />
        <q-btn
          v-if="applyLabel"
          class="apply-button"
          color="primary"
          no-caps
          :disable="applyDisabled || applying"
          :loading="applying"
          :label="applyLabel"
          @click="$emit('apply')"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<style scoped>
.preview-dialog {
  width: min(62rem, 96vw);
  max-width: none;
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.preview-header,
.preview-actions {
  padding: var(--gap-md-lg) 1.25rem;
  flex-shrink: 0;
}
.preview-header {
  padding-block-end: var(--gap-md);
}
.preview-title {
  margin: 0;
  color: var(--text-bright);
  font-size: 1.375rem;
  font-weight: 700;
}
.preview-workspace {
  display: grid;
  gap: 1rem;
  align-items: start;
  padding: 0 1.25rem var(--gap-md-lg);
  overflow: auto;
}
.preview-workspace.has-controls {
  grid-template-columns: minmax(0, 1fr) 14rem;
}
.preview-column {
  min-width: 0;
}
.preview-viewport {
  position: relative;
  width: 100%;
  margin-inline: auto;
  overflow: hidden;
  border: 1px solid var(--border-color);
  background: #11131a;
}
.preview-actions {
  gap: var(--gap-sm);
  border-block-start: 1px solid var(--border-color);
}
@media (max-width: 56rem) {
  .preview-workspace.has-controls {
    grid-template-columns: 1fr;
  }
}
</style>
