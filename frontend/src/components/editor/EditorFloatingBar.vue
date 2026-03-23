<script lang="ts" setup>
import ShortcutsPopup from "./ShortcutsPopup.vue";
import { KEY_LABELS } from "@/composables/shortcutKeys";
import { useUndoStack } from "@/composables/useUndoStack";
import { useI18n } from "vue-i18n";
import {
  symOutlinedKeyboard,
  symOutlinedRedo,
  symOutlinedUndo,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const undoStack = useUndoStack();
</script>

<template>
  <div class="floating-bar row no-wrap items-center">
    <q-btn flat dense round :icon="symOutlinedUndo" :disable="!undoStack.canUndo.value" @click="undoStack.undo()">
      <q-tooltip>{{ KEY_LABELS.undo }}</q-tooltip>
    </q-btn>
    <q-btn flat dense round :icon="symOutlinedRedo" :disable="!undoStack.canRedo.value" @click="undoStack.redo()">
      <q-tooltip>{{ KEY_LABELS.redo }}</q-tooltip>
    </q-btn>
    <q-separator vertical class="q-mx-xs" />
    <q-btn flat dense round :icon="symOutlinedKeyboard" :aria-label="t('shortcuts.title')">
      <q-tooltip>{{ t("shortcuts.title") }}</q-tooltip>
      <q-popup-proxy transition-show="scale" transition-hide="scale">
        <ShortcutsPopup />
      </q-popup-proxy>
    </q-btn>
  </div>
</template>

<style lang="scss" scoped>
.floating-bar {
  position: fixed;
  bottom: 3.5rem;
  left: var(--gap-lg);
  z-index: 100;
  padding: var(--gap-xs) var(--gap-sm);
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}
</style>
