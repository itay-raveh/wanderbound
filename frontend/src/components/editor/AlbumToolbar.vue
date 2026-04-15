<script lang="ts" setup>
import type { Album } from "@/client";
import { useUndoStack } from "@/composables/useUndoStack";
import { KEY_LABELS } from "@/composables/shortcutKeys";
import ShortcutsPopup from "./ShortcutsPopup.vue";
import PdfExportButton from "./PdfExportButton.vue";

import {
  editorZoom,
  setEditorZoom,
  MIN_ZOOM,
  MAX_ZOOM,
  ZOOM_STEP,
} from "@/composables/useEditorZoom";
import {
  symOutlinedKeyboard,
  symOutlinedRedo,
  symOutlinedUndo,
  symOutlinedZoomIn,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

defineProps<{
  album?: Album;
}>();

const undoStack = useUndoStack();
</script>

<template>
  <div class="album-toolbar row no-wrap items-center">
    <div
      v-if="album"
      class="toolbar-actions row no-wrap items-center"
      role="toolbar"
      :aria-label="t('editor.toolbar')"
    >
      <q-btn
        class="action-btn"
        flat
        dense
        round
        :icon="symOutlinedUndo"
        :disable="!undoStack.canUndo.value"
        :aria-label="t('shortcuts.undo')"
        @click="undoStack.undo()"
      >
        <q-tooltip>{{ KEY_LABELS.undo }}</q-tooltip>
      </q-btn>
      <q-btn
        class="action-btn"
        flat
        dense
        round
        :icon="symOutlinedRedo"
        :disable="!undoStack.canRedo.value"
        :aria-label="t('shortcuts.redo')"
        @click="undoStack.redo()"
      >
        <q-tooltip>{{ KEY_LABELS.redo }}</q-tooltip>
      </q-btn>
      <q-btn
        class="keyboard-btn"
        flat
        dense
        round
        :icon="symOutlinedKeyboard"
        :aria-label="t('shortcuts.title')"
      >
        <q-tooltip
          transition-show="scale"
          transition-hide="scale"
          class="q-menu"
          ><ShortcutsPopup
        /></q-tooltip>
      </q-btn>
      <q-separator vertical class="action-divider" />
      <div class="zoom-control row no-wrap items-center">
        <q-icon
          :name="symOutlinedZoomIn"
          size="var(--type-md)"
          class="text-muted"
        />
        <q-slider
          :model-value="editorZoom"
          :min="MIN_ZOOM"
          :max="MAX_ZOOM"
          :step="ZOOM_STEP"
          snap
          class="zoom-slider"
          :aria-label="t('editor.zoom')"
          @change="setEditorZoom"
        />
        <span class="zoom-label text-muted"
          >{{ Math.round(editorZoom * 100) }}%</span
        >
      </div>
      <q-separator vertical class="action-divider" />
      <PdfExportButton v-if="album" :album-id="album.id" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.album-toolbar {
  gap: var(--gap-lg);
}

.toolbar-actions {
  margin-inline-start: auto;
  gap: var(--gap-md-lg);
  overflow-x: auto;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }
}

.action-btn {
  color: var(--text-bright);

  :deep(.q-focus-helper) {
    background: color-mix(in srgb, var(--q-primary) 12%, transparent);
    opacity: 1;
  }

  &:hover :deep(.q-focus-helper) {
    background: color-mix(in srgb, var(--q-primary) 22%, transparent);
  }

  &.disabled {
    color: var(--text-muted);

    :deep(.q-focus-helper) {
      opacity: 0;
    }
  }
}

.keyboard-btn {
  color: var(--text-muted);
  transition: color var(--duration-fast);

  &:hover {
    color: var(--text-bright);
  }
}

.zoom-control {
  gap: var(--gap-md);
}

.zoom-slider {
  width: 5rem;
}

.zoom-label {
  font-size: var(--type-xs);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  min-width: 2.5rem;
}

.action-divider {
  margin-inline: var(--gap-sm);
  opacity: 0.5;
}

@media (prefers-reduced-motion: reduce) {
  .keyboard-btn {
    transition: none;
  }
}
</style>
