import type { AlbumChapter } from "@/client";
import {
  usePdfExportStream,
  type PdfExportTarget,
} from "@/composables/usePdfExportStream";
import { qualitySummary } from "@/composables/usePhotoQuality";
import { computed, ref } from "vue";
import { usePdfChapterSelection } from "./usePdfChapterSelection";

export function usePdfExportController(
  albumId: () => string,
  chapters: () => AlbumChapter[],
) {
  const exportTarget = ref<PdfExportTarget>({ type: "album" });
  const pdf = usePdfExportStream(albumId, () => exportTarget.value);
  const showChapterDialog = ref(false);
  const showQualityDialog = ref(false);
  const chapterSelection = usePdfChapterSelection(chapters);

  const progressFraction = computed(() => {
    const progress = pdf.progress.value;
    if (progress.phase === "loading" && progress.total) {
      return progress.done / progress.total;
    }
    if (progress.phase === "rendering") return 1;
    return 0;
  });

  const buttonState = computed(() =>
    pdf.state.value === "done" || pdf.state.value === "running"
      ? pdf.state.value
      : "idle",
  );

  function startExport(target: PdfExportTarget) {
    exportTarget.value = target;
    const summary = qualitySummary.value;
    if (summary.caution > 0 || summary.warning > 0) {
      showQualityDialog.value = true;
      return;
    }
    pdf.start();
  }

  function openExportDialog() {
    if (chapterSelection.chapterOptions.value.length === 0) {
      startExport({ type: "album" });
      return;
    }
    showChapterDialog.value = true;
  }

  function confirmChapterExport() {
    const target = chapterSelection.selectedExportTarget();
    if (!target) return;
    showChapterDialog.value = false;
    startExport(target);
  }

  function confirmQualityWarning() {
    showQualityDialog.value = false;
    pdf.start();
  }

  return {
    pdf,
    qualitySummary,
    showChapterDialog,
    showQualityDialog,
    progressFraction,
    buttonState,
    openExportDialog,
    confirmChapterExport,
    confirmQualityWarning,
    ...chapterSelection,
  };
}
