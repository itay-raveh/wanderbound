<script lang="ts" setup>
import { usePdfExportStream } from "@/composables/usePdfExportStream";
import { qualitySummary } from "@/composables/usePhotoQuality";
import AsyncActionButton from "@/components/ui/AsyncActionButton.vue";
import QualityWarningDialog from "./QualityWarningDialog.vue";
import { symOutlinedPictureAsPdf } from "@quasar/extras/material-symbols-outlined";
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

const buttonState = computed(() =>
  pdf.state.value === "done" || pdf.state.value === "running"
    ? pdf.state.value
    : "idle",
);

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
  <AsyncActionButton
    :state="buttonState"
    :idle-icon="symOutlinedPictureAsPdf"
    :idle-label="t('editor.exportPdf')"
    :progress-fraction="progressFraction"
    :progress-message="pdf.progress.value.message"
    :done-message="t('pdf.ready')"
    @start="onExportPdf"
    @cancel="pdf.abort()"
  />

  <QualityWarningDialog
    v-model="showQualityDialog"
    :caution="qualitySummary.caution"
    :warning="qualitySummary.warning"
    @confirm="onConfirmExport"
  />
</template>
