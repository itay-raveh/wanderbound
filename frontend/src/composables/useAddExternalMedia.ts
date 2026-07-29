import { t } from "@/i18n";
import { EXTERNAL_MEDIA_IMPORT_MAX_ITEMS } from "@/utils/externalMediaLimits";
import { useQueryCache } from "@pinia/colada";
import { computed, nextTick, ref } from "vue";
import {
  applyImportResult,
  invalidateExternalMediaQueries,
  runGoogleImportStream,
  uploadDeviceFiles,
  type ExternalImportTarget,
  type ImportCompleted,
} from "./externalMediaImport";
import { useGooglePhotos } from "./useGooglePhotos";
import { useGooglePhotosPicker } from "./useGooglePhotosPicker";
import { useMediaOperationState } from "./useMediaOperationState";

export type { ExternalImportTarget } from "./externalMediaImport";

type AddPhase =
  | "idle"
  | "authorizing"
  | "picking"
  | "uploading"
  | "processing"
  | "done"
  | "error";

interface ImportProgress {
  done: number;
  total: number;
}

const DONE_RESET_MS = 2500;

export function useAddExternalMedia(albumId: () => string) {
  const cache = useQueryCache();
  const googlePhotos = useGooglePhotos();
  const operation = useMediaOperationState<AddPhase>("idle", "error");
  const picker = useGooglePhotosPicker(googlePhotos, {
    blocked: t("mediaImport.errors.popupBlocked"),
    loading: t("mediaImport.authorizing"),
    timeout: t("mediaImport.errors.selectionTimeout"),
  });
  const progress = ref<ImportProgress>({ done: 0, total: 0 });
  const importedCount = ref(0);
  let resetTimer: ReturnType<typeof setTimeout> | null = null;

  const isBusy = computed(() =>
    ["authorizing", "picking", "uploading", "processing"].includes(
      operation.phase.value,
    ),
  );

  function reset() {
    operation.abort();
    operation.clearError();
    progress.value = { done: 0, total: 0 };
    importedCount.value = 0;
    picker.cleanup();
  }

  function begin(): AbortSignal {
    if (resetTimer !== null) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
    reset();
    return operation.begin();
  }

  async function complete(
    result: ImportCompleted,
    target: ExternalImportTarget,
  ) {
    applyImportResult(cache, albumId(), result, target);
    await nextTick();
    await invalidateExternalMediaQueries(cache, albumId(), target);
    importedCount.value = result.names.length;
    operation.phase.value = "done";
    resetTimer = setTimeout(() => {
      operation.phase.value = "idle";
      reset();
      resetTimer = null;
    }, DONE_RESET_MS);
  }

  async function importDevice(
    files: FileList | File[],
    target: ExternalImportTarget,
  ): Promise<ImportCompleted | undefined> {
    const selected = Array.from(files);
    if (selected.length === 0) return;
    if (selected.length > EXTERNAL_MEDIA_IMPORT_MAX_ITEMS) {
      operation.setError(t("mediaImport.errors.tooMany"));
      return;
    }

    const signal = begin();
    operation.phase.value = "uploading";
    progress.value = { done: 0, total: 1 };
    try {
      const result = await uploadDeviceFiles(
        albumId(),
        selected,
        target,
        signal,
      );
      operation.phase.value = "processing";
      await complete(result, target);
      return result;
    } catch (error) {
      operation.fail(error, t("mediaImport.error"));
    }
  }

  async function importGoogle(
    target: ExternalImportTarget,
  ): Promise<ImportCompleted | undefined> {
    const signal = begin();
    try {
      picker.open();
      if (!picker.isConnected.value) {
        operation.phase.value = "authorizing";
        await picker.authorize(signal);
      }
      operation.phase.value = "picking";
      const sessionId = await picker.pick(signal, {
        maxItemCount: EXTERNAL_MEDIA_IMPORT_MAX_ITEMS,
        checkAbortedAfterPoll: true,
      });
      operation.phase.value = "processing";
      const result = await runGoogleImportStream(
        albumId(),
        sessionId,
        target,
        signal,
        (done, total) => (progress.value = { done, total }),
      );
      await complete(result, target);
      return result;
    } catch (error) {
      operation.fail(error, t("mediaImport.error"));
    } finally {
      picker.cleanup();
    }
  }

  function cancel() {
    operation.cancel();
    reset();
  }

  return {
    phase: operation.phase,
    progress,
    importedCount,
    errorDetail: operation.errorDetail,
    isBusy,
    googlePhotosState: picker.state,
    importDevice,
    importGoogle,
    cancel,
  };
}
