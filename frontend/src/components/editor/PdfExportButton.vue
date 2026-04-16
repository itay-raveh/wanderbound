<script lang="ts" setup>
import { usePdfExportStream } from "@/composables/usePdfExportStream";
import { qualitySummary } from "@/composables/usePhotoQuality";
import ProgressBar from "@/components/ui/ProgressBar.vue";
import QualityWarningDialog from "./QualityWarningDialog.vue";
import {
  symOutlinedClose,
  symOutlinedCheck,
  symOutlinedPictureAsPdf,
} from "@quasar/extras/material-symbols-outlined";
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";

const { t } = useI18n();

const props = defineProps<{ albumId: string }>();

const pdf = usePdfExportStream(() => props.albumId);
const showQualityDialog = ref(false);

const progressFraction = computed(() => {
  const p = pdf.progress.value;
  if (p.phase === "loading" && p.total) return p.done / p.total;
  if (p.phase === "rendering") return 1; // full bar with shimmer
  return 0;
});

function onExportPdf() {
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
  <button
    v-if="pdf.state.value === 'done'"
    class="export-btn done"
    aria-disabled="true"
    :aria-label="t('pdf.ready')"
  >
    <q-icon :name="symOutlinedCheck" size="var(--type-lg)" class="done-icon" />
    {{ t("pdf.ready") }}
  </button>

  <button
    v-else-if="pdf.state.value === 'running'"
    class="export-btn running"
    :aria-label="t('pdf.cancel')"
    aria-busy="true"
    @click="pdf.abort()"
  >
    <div class="progress-content">
      <q-icon
        :name="symOutlinedClose"
        size="var(--type-md)"
        class="cancel-icon"
      />
      <span class="progress-text" aria-live="polite">{{
        pdf.progress.value.message
      }}</span>
    </div>
    <ProgressBar :progress="progressFraction" />
  </button>

  <button
    v-else
    class="export-btn"
    :aria-label="t('editor.exportPdf')"
    @click="onExportPdf"
  >
    <q-icon :name="symOutlinedPictureAsPdf" size="var(--type-lg)" />
    {{ t("editor.exportPdf") }}
  </button>

  <QualityWarningDialog
    v-model="showQualityDialog"
    :caution="qualitySummary.caution"
    :warning="qualitySummary.warning"
    @confirm="onConfirmExport"
  />
</template>

<style lang="scss" scoped>
@use "@/styles/action-button" as *;
@include action-button;
</style>
