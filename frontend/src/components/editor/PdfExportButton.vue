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
.export-btn {
  font-family: var(--font-ui);
  font-size: var(--type-sm);
  font-weight: 500;
  color: var(--q-primary);
  border: 1px solid var(--q-primary);
  padding: var(--gap-sm) var(--gap-md-lg);
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--gap-sm);
  min-height: 2.75rem;
  white-space: nowrap;
  transition:
    background var(--duration-fast),
    color var(--duration-fast),
    border-color var(--duration-fast);

  &:hover:not([aria-disabled]):not(.running) {
    background: var(--q-primary);
    color: var(--bg);
  }

  &:focus-visible {
    outline: 0.125rem solid var(--q-primary);
    outline-offset: 0.125rem;
  }
}

.export-btn.running {
  border-color: var(--border-color);
  color: var(--text-muted);
  cursor: pointer;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: var(--gap-xs);
  min-width: 10rem;

  &:hover {
    border-color: var(--text-faint);

    .cancel-icon {
      color: var(--text);
    }
  }
}

.progress-content {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}

.cancel-icon {
  color: var(--text-faint);
  transition: color var(--duration-fast);
}

.progress-text {
  font-size: var(--type-xs);
  font-variant-numeric: tabular-nums;
}

.export-btn.done {
  border-color: var(--q-primary);
  color: var(--q-primary);
  cursor: default;
}

.done-icon {
  animation: scale-in var(--duration-normal) cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes scale-in {
  from {
    transform: scale(0);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .done-icon {
    animation: none;
  }
}
</style>
