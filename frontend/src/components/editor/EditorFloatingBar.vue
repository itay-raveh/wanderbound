<script lang="ts" setup>
import ShortcutsPopup from "./ShortcutsPopup.vue";
import { KEY_LABELS } from "@/composables/shortcutKeys";
import { useUndoStack } from "@/composables/useUndoStack";
import { useEditorHints } from "@/composables/useEditorHints";
import { useI18n } from "vue-i18n";
import {
  symOutlinedHelp,
  symOutlinedKeyboard,
  symOutlinedRedo,
  symOutlinedUndo,
} from "@quasar/extras/material-symbols-outlined";

const { t } = useI18n();
const undoStack = useUndoStack();
const { bannerDismissed, resetHints } = useEditorHints();
</script>

<template>
  <div class="floating-bar row no-wrap items-center fade-up">
    <q-btn flat dense round :icon="symOutlinedUndo" :disable="!undoStack.canUndo.value" :aria-label="t('shortcuts.undo')" @click="undoStack.undo()">
      <q-tooltip>{{ KEY_LABELS.undo }}</q-tooltip>
    </q-btn>
    <q-btn flat dense round :icon="symOutlinedRedo" :disable="!undoStack.canRedo.value" :aria-label="t('shortcuts.redo')" @click="undoStack.redo()">
      <q-tooltip>{{ KEY_LABELS.redo }}</q-tooltip>
    </q-btn>
    <q-separator vertical class="q-mx-xs" />
    <q-btn flat dense round :icon="symOutlinedKeyboard" :aria-label="t('shortcuts.title')">
      <q-tooltip>{{ t("shortcuts.title") }}</q-tooltip>
      <q-popup-proxy transition-show="scale" transition-hide="scale">
        <ShortcutsPopup />
      </q-popup-proxy>
    </q-btn>
    <Transition name="fade">
      <q-btn
        v-if="bannerDismissed"
        flat dense round
        :icon="symOutlinedHelp"
        :aria-label="t('onboarding.showTips')"
        @click="resetHints"
      >
        <q-tooltip>{{ t("onboarding.showTips") }}</q-tooltip>
      </q-btn>
    </Transition>
  </div>
</template>

<style lang="scss" scoped>
.floating-bar {
  position: fixed;
  bottom: 3.5rem;
  left: calc(var(--drawer-width, 0px) + var(--gap-lg));
  z-index: 100;
  padding: var(--gap-sm) var(--gap-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  gap: var(--gap-xs);
  transition: box-shadow var(--duration-fast);

  &:hover {
    box-shadow: var(--shadow-lg);
  }
}
</style>
