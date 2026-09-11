<script setup lang="ts">
import { useId } from "vue";
import { useI18n } from "vue-i18n";

const show = defineModel<boolean>({ required: true });
defineProps<{
  title: string;
  previewLabel: string;
  aspectRatio?: number;
  maximized?: boolean;
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
    :maximized="maximized"
    :aria-labelledby="id"
    :persistent="persistent || applying"
  >
    <q-card class="preview-dialog" :class="{ maximized }">
      <q-card-section class="preview-header">
        <h2 :id="id" class="preview-title">{{ title }}</h2>
        <slot name="header" />
      </q-card-section>
      <q-card-section
        class="preview-workspace"
        :class="{ 'has-controls': $slots.controls && !controlsBelow }"
      >
        <slot v-if="$slots.workspace" name="workspace" />
        <div v-else class="preview-column">
          <div
            class="preview-viewport"
            :style="{
              aspectRatio: String(aspectRatio),
              maxWidth: aspectRatio ? `${aspectRatio * 56}vh` : undefined,
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
        <slot name="actions" />
        <q-btn
          class="cancel-button"
          :autofocus="maximized"
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
  padding: var(--gap-md-lg) var(--gap-lg);
  flex-shrink: 0;
}
.preview-header {
  display: flex;
  align-items: center;
  gap: var(--gap-lg);
}
.preview-title {
  margin: 0;
  color: var(--text-bright);
  font-size: var(--type-xl);
  line-height: 1.2;
  font-weight: 700;
}
.preview-workspace {
  display: grid;
  gap: var(--gap-lg);
  align-items: start;
  padding: 0 var(--gap-lg) var(--gap-md-lg);
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
  background: var(--bg);
}
.preview-actions {
  gap: var(--gap-sm);
  border-block-start: 1px solid var(--border-color);
}
.maximized {
  width: 100%;
  height: 100%;
  max-height: none;
  background: var(--bg);
  color: var(--text);
}
.maximized .preview-workspace {
  display: flex;
  align-items: stretch;
  flex: 1;
  min-height: 0;
  padding: var(--gap-lg);
}
.maximized .preview-header,
.maximized .preview-actions {
  background: var(--surface);
}
.maximized .preview-header {
  border-block-end: 1px solid var(--border-color);
}
.preview-dialog :deep(.q-btn) {
  min-width: 2.75rem;
  min-height: 2.75rem;
}
.preview-dialog :deep(:focus-visible) {
  outline: 2px solid var(--primary-text) !important;
  outline-offset: -2px;
}
@media (max-width: 56rem) {
  .preview-workspace.has-controls {
    grid-template-columns: 1fr;
  }
}
</style>
