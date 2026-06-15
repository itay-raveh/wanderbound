<script lang="ts" setup>
import type { AlbumChapter } from "@/client";
import {
  usePdfExportStream,
  type PdfExportTarget,
} from "@/composables/usePdfExportStream";
import { qualitySummary } from "@/composables/usePhotoQuality";
import AsyncActionButton from "@/components/ui/AsyncActionButton.vue";
import QualityWarningDialog from "./QualityWarningDialog.vue";
import { symOutlinedPictureAsPdf } from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";

const { t } = useI18n();

const props = defineProps<{ albumId: string; chapters?: AlbumChapter[] }>();

const exportTarget = ref<PdfExportTarget>({ type: "album" });
const pdf = usePdfExportStream(
  () => props.albumId,
  () => exportTarget.value,
);
const showQualityDialog = ref(false);

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

const chapterOptions = computed(() => props.chapters ?? []);
</script>

<template>
  <AsyncActionButton
    :state="buttonState"
    :idle-icon="symOutlinedPictureAsPdf"
    :idle-label="t('editor.exportPdf')"
    :progress-fraction="progressFraction"
    :progress-message="pdf.progress.value.message"
    :done-message="t('pdf.ready')"
    @start="startExport({ type: 'album' })"
    @cancel="pdf.abort()"
  />

  <q-btn-dropdown
    v-if="chapterOptions.length"
    flat
    dense
    no-caps
    class="chapter-export-menu"
    :label="t('editor.moreExports')"
  >
    <q-list dense>
      <q-item
        v-for="(chapter, index) in chapterOptions"
        :key="chapter.id"
        clickable
        v-close-popup
        @click="
          startExport({
            type: 'chapter',
            id: chapter.id,
          })
        "
      >
        <q-item-section>
          {{
            t("editor.exportChapter", {
              name:
                chapter.title || t("chapters.untitled", { number: index + 1 }),
            })
          }}
        </q-item-section>
      </q-item>
      <q-separator />
      <q-item
        clickable
        v-close-popup
        @click="startExport({ type: 'chapters' })"
      >
        <q-item-section>{{ t("editor.exportAllChapters") }}</q-item-section>
      </q-item>
    </q-list>
  </q-btn-dropdown>

  <QualityWarningDialog
    v-model="showQualityDialog"
    :caution="qualitySummary.caution"
    :warning="qualitySummary.warning"
    @confirm="onConfirmExport"
  />
</template>

<style lang="scss" scoped>
.chapter-export-menu {
  color: var(--text-muted);
}
</style>
