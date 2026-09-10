<script lang="ts" setup>
import type { AlbumChapter } from "@/client";
import AsyncActionButton from "@/components/ui/AsyncActionButton.vue";
import PromptDialog from "@/components/ui/PromptDialog.vue";
import QualityWarningDialog from "./QualityWarningDialog.vue";
import { usePdfExportController } from "./usePdfExportController";
import { symOutlinedPictureAsPdf } from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
const props = defineProps<{ albumId: string; chapters?: AlbumChapter[] }>();

const {
  pdf,
  separate,
  qualitySummary,
  showChapterDialog,
  showQualityDialog,
  progressFraction,
  buttonState,
  chapterOptionItems,
  selectedChapterIds,
  selectedCount,
  allChaptersSelected,
  someChaptersSelected,
  openExportDialog,
  confirmChapterExport,
  confirmQualityWarning,
} = usePdfExportController(
  () => props.albumId,
  () => props.chapters ?? [],
);
</script>

<template>
  <AsyncActionButton
    :state="buttonState"
    :idle-icon="symOutlinedPictureAsPdf"
    :idle-label="t('editor.exportPdf')"
    :progress-fraction="progressFraction"
    :progress-message="pdf.progress.value.message"
    :done-message="t('pdf.ready')"
    @start="openExportDialog"
    @cancel="pdf.abort()"
  />

  <PromptDialog
    v-model="showChapterDialog"
    :icon="symOutlinedPictureAsPdf"
    variant="primary"
    :title="t('editor.exportChaptersTitle')"
    body=""
    :confirm-label="t('editor.exportSelectedChapters')"
    :cancel-label="t('common.cancel')"
    :confirm-disabled="selectedCount === 0"
    @confirm="confirmChapterExport"
  >
    <q-option-group
      v-model="separate"
      :options="[
        { label: t('print.combined'), value: false },
        { label: t('print.separate'), value: true },
      ]"
      class="q-mb-md"
    />
    <p class="export-hint">
      {{ t(separate ? "print.separateHint" : "print.combinedHint") }}
    </p>
    <div class="chapter-export-selector">
      <q-checkbox
        v-model="allChaptersSelected"
        :indeterminate="someChaptersSelected"
        :label="t('editor.allChapters')"
        class="chapter-export-check all"
      />
      <q-separator />
      <q-option-group
        v-model="selectedChapterIds"
        type="checkbox"
        :options="chapterOptionItems"
        class="chapter-export-options"
      />
    </div>
  </PromptDialog>

  <QualityWarningDialog
    v-model="showQualityDialog"
    :caution="qualitySummary.caution"
    :warning="qualitySummary.warning"
    @confirm="confirmQualityWarning"
  />
</template>

<style lang="scss" scoped>
.export-hint {
  text-align: start;
  font-size: var(--type-sm);
}

.chapter-export-selector {
  text-align: start;
  min-width: min(24rem, calc(100vw - 6rem));
  margin: 0 0 var(--gap-lg);
}

.chapter-export-check {
  width: 100%;
  font-size: var(--type-sm);
  color: var(--text-bright);

  &.all {
    margin-block-end: var(--gap-sm);
    font-weight: 600;
  }
}

.chapter-export-options {
  margin-block: var(--gap-sm);

  :deep(.q-checkbox) {
    width: 100%;
    padding-block: var(--gap-xs);
    font-size: var(--type-sm);
  }
}
</style>
