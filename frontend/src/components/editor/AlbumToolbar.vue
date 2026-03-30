<script lang="ts" setup>
import type { Album } from "@/client";
import { usePdfExportStream } from "@/composables/usePdfExportStream";
import { useAlbumMutation } from "@/queries/useAlbumMutation";
import { useUndoStack } from "@/composables/useUndoStack";
import { KEY_LABELS } from "@/composables/shortcutKeys";
import { ALLOWED_FONTS, DEFAULT_BODY_FONT, DEFAULT_FONT } from "@/utils/fonts";
import ShortcutsPopup from "./ShortcutsPopup.vue";

import {
  symOutlinedKeyboard,
  symOutlinedPictureAsPdf,
  symOutlinedRedo,
  symOutlinedUndo,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { computed } from "vue";

const { t } = useI18n();

const props = defineProps<{
  album?: Album;
}>();

const pdf = usePdfExportStream(() => props.album?.id ?? "");
const pdfBusy = computed(
  () => pdf.state.value !== "idle" && pdf.state.value !== "error",
);
const undoStack = useUndoStack();
const albumMutation = useAlbumMutation(() => props.album?.id ?? "");

const currentFont = computed(() => props.album?.font ?? DEFAULT_FONT);
const currentBodyFont = computed(
  () => props.album?.body_font ?? DEFAULT_BODY_FONT,
);

function onExportPdf() {
  if (!props.album) return;
  pdf.start();
}

function updateFont(font: string) {
  albumMutation.mutate({ font });
}

function updateBodyFont(font: string) {
  albumMutation.mutate({ body_font: font });
}
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
      <div class="font-pickers row no-wrap items-center">
        <q-select
          :model-value="currentFont"
          :options="ALLOWED_FONTS"
          :label="t('editor.font')"
          dense
          borderless
          options-dense
          class="font-picker"
          @update:model-value="updateFont"
        >
          <template #option="{ itemProps, opt }">
            <q-item v-bind="itemProps" :style="{ fontFamily: opt }">
              <q-item-section>{{ opt }}</q-item-section>
            </q-item>
          </template>
        </q-select>
        <q-select
          :model-value="currentBodyFont"
          :options="ALLOWED_FONTS"
          :label="t('editor.bodyFont')"
          dense
          borderless
          options-dense
          class="font-picker"
          @update:model-value="updateBodyFont"
        >
          <template #option="{ itemProps, opt }">
            <q-item v-bind="itemProps" :style="{ fontFamily: opt }">
              <q-item-section>{{ opt }}</q-item-section>
            </q-item>
          </template>
        </q-select>
      </div>
      <q-btn
        flat
        no-caps
        dense
        :disable="pdfBusy"
        :aria-busy="pdfBusy"
        class="export-btn"
        @click="onExportPdf"
      >
        <q-icon
          :name="symOutlinedPictureAsPdf"
          size="var(--type-lg)"
          class="q-mr-xs"
        />
        {{ t("editor.exportPdf") }}
      </q-btn>
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

.export-btn {
  color: var(--q-primary);
  border: 0.0625rem solid var(--q-primary);
  padding: var(--gap-sm) var(--gap-md-lg);
  transition:
    background var(--duration-fast),
    color var(--duration-fast);

  :deep(.q-focus-helper) {
    display: none;
  }

  &:hover:not(.disabled) {
    background: var(--q-primary);
    color: #fff; // white-on-primary — standard Quasar convention
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }

  &.disabled {
    opacity: 0.4;
    border-color: var(--text-faint);
    color: var(--text-faint);
  }
}

.font-pickers {
  gap: var(--gap-md);
}

.font-picker {
  width: 11rem;
  border-bottom: 0.0625rem solid var(--text-faint);
  transition: border-color var(--duration-fast);

  &:hover {
    border-color: var(--text-muted);
  }

  &:focus-within {
    border-color: var(--q-primary);
  }
}

.action-divider {
  margin-inline: var(--gap-sm);
  opacity: 0.5;
}

@media (prefers-reduced-motion: reduce) {
  .keyboard-btn,
  .export-btn,
  .font-picker {
    transition: none;
  }
}
</style>
