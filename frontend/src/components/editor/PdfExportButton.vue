<script lang="ts" setup>
import type { AlbumChapter } from "@/client";
import {
  usePdfExportStream,
  type PdfExportTarget,
} from "@/composables/usePdfExportStream";
import { qualitySummary } from "@/composables/usePhotoQuality";
import AsyncActionButton from "@/components/ui/AsyncActionButton.vue";
import PromptDialog from "@/components/ui/PromptDialog.vue";
import QualityWarningDialog from "./QualityWarningDialog.vue";
import { symOutlinedPictureAsPdf } from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { computed, ref, watch } from "vue";

const { t } = useI18n();

const props = defineProps<{ albumId: string; chapters?: AlbumChapter[] }>();

const exportTarget = ref<PdfExportTarget>({ type: "album" });
const pdf = usePdfExportStream(
  () => props.albumId,
  () => exportTarget.value,
);
const showChapterDialog = ref(false);
const showQualityDialog = ref(false);
const selectedChapterIds = ref<string[]>([]);

const progressFraction = computed(() => {
  const p = pdf.progress.value;
  if (p.phase === "loading" && p.total) return p.done / p.total;
  if (p.phase === "rendering") return 1; // full bar with shimmer
  return 0;
});

const buttonState = computed(() =>
  pdf.state.value === "done" || pdf.state.value === "running"
    ? pdf.state.value
    : "idle",
);

const chapterOptions = computed(() => props.chapters ?? []);

const selectedCount = computed(() => selectedChapterIds.value.length);

const allChaptersSelected = computed({
  get: () =>
    chapterOptions.value.length > 0 &&
    selectedChapterIds.value.length === chapterOptions.value.length,
  set: (checked: boolean) => {
    selectedChapterIds.value = checked
      ? chapterOptions.value.map((chapter) => chapter.id)
      : [];
  },
});

const someChaptersSelected = computed(
  () =>
    selectedChapterIds.value.length > 0 &&
    selectedChapterIds.value.length < chapterOptions.value.length,
);

const exportSummary = computed(() => {
  if (selectedCount.value === 1) return t("editor.exportSelectionSingle");
  return t("editor.exportSelectionZip", { count: selectedCount.value });
});

watch(
  chapterOptions,
  (chapters) => {
    const valid = new Set(chapters.map((chapter) => chapter.id));
    const kept = selectedChapterIds.value.filter((id) => valid.has(id));
    selectedChapterIds.value =
      kept.length > 0 ? kept : chapters.map((chapter) => chapter.id);
  },
  { immediate: true },
);

function chapterLabel(chapter: AlbumChapter, index: number) {
  return chapter.title || t("chapters.untitled", { number: index + 1 });
}

function openExportDialog() {
  if (chapterOptions.value.length === 0) {
    startExport({ type: "album" });
    return;
  }
  showChapterDialog.value = true;
}

function confirmChapterExport() {
  const ids = selectedChapterIds.value;
  if (ids.length === 0) return;
  showChapterDialog.value = false;
  startExport(
    ids.length === 1 ? { type: "chapter", id: ids[0] } : { type: "chapters", ids },
  );
}

function startExport(target: PdfExportTarget) {
  exportTarget.value = target;
  const q = qualitySummary.value;
  if (q.caution > 0 || q.warning > 0) {
    showQualityDialog.value = true;
    return;
  }
  pdf.start();
}

function onConfirmExport() {
  showQualityDialog.value = false;
  pdf.start();
}
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
    :body="t('editor.exportChaptersBody')"
    :confirm-label="t('editor.exportSelectedChapters')"
    :cancel-label="t('common.cancel')"
    :confirm-disabled="selectedCount === 0"
    @confirm="confirmChapterExport"
  >
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
        :options="
          chapterOptions.map((chapter, index) => ({
            label: chapterLabel(chapter, index),
            value: chapter.id,
          }))
        "
        class="chapter-export-options"
      />
      <p
        class="chapter-export-summary text-muted"
        aria-live="polite"
        data-testid="chapter-export-summary"
      >
        {{ exportSummary }}
      </p>
    </div>
  </PromptDialog>

  <QualityWarningDialog
    v-model="showQualityDialog"
    :caution="qualitySummary.caution"
    :warning="qualitySummary.warning"
    @confirm="onConfirmExport"
  />
</template>

<style lang="scss" scoped>
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

.chapter-export-summary {
  font-size: var(--type-xs);
  margin: var(--gap-sm) 0 0;
}
</style>
