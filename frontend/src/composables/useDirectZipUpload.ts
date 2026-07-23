import {
  completeIngestion,
  pendingUpload,
  selectUploadTrips,
  uploadProgress as streamUploadProgress,
  type TripChoice,
  type UploadProgressResponse,
  type UploadProgressUpdate,
  type UploadResult,
} from "@/client";
import AwsS3 from "@uppy/aws-s3";
import Uppy, { type UppyFile } from "@uppy/core";
import { onScopeDispose, ref } from "vue";

const PART_SIZE = 64 * 1024 * 1024;
const COMPLETION_ATTEMPTS = 3;
const STREAM_CONNECTIONS = 3;

type UploadState =
  | "idle"
  | "uploading"
  | "processing"
  | "selecting"
  | "failed";
type UploadIngestionPhase = UploadProgressUpdate["phase"];
type UploadProgressEvent = UploadProgressResponse[number];
type UploadMeta = { size_bytes?: number };
type UploadBody = Record<string, unknown>;
type MultipartFile = UppyFile<UploadMeta, UploadBody> & {
  s3Multipart?: { uploadId?: string };
};

const INGESTION_PHASE_ORDER: Record<UploadIngestionPhase, number> = {
  downloading: 0,
  validating: 1,
  importing: 2,
};

class UploadIngestionError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.code = code;
  }
}

async function claimCompletedUpload(
  uploadId: string,
  signal: AbortSignal,
): Promise<UploadResult> {
  for (let attempt = 0; attempt < COMPLETION_ATTEMPTS; attempt += 1) {
    try {
      const { data } = await completeIngestion({
        path: { upload_id: uploadId },
        signal,
        throwOnError: true,
      });
      return data;
    } catch (error) {
      if (signal.aborted || attempt === COMPLETION_ATTEMPTS - 1) throw error;
      await new Promise((resolve) => setTimeout(resolve, 250 * 2 ** attempt));
    }
  }
  throw new UploadIngestionError("upload_failed");
}

export async function followUploadIngestion(
  uploadId: string,
  signal: AbortSignal,
  onProgress: (event: UploadProgressUpdate) => void,
  onSelection: (choices: TripChoice[]) => void = () => {},
): Promise<UploadResult> {
  let lastProgress: UploadProgressUpdate | null = null;
  for (let connection = 0; connection < STREAM_CONNECTIONS; connection += 1) {
    if (signal.aborted) break;
    let lastStreamError: unknown = null;
    const { stream } = await streamUploadProgress({
      path: { upload_id: uploadId },
      signal,
      sseMaxRetryAttempts: 4,
      sseMaxRetryDelay: 5_000,
      onSseError: (error) => {
        lastStreamError = error;
      },
      throwOnError: true,
    });
    for await (const raw of stream) {
      lastStreamError = null;
      const event = raw as unknown as UploadProgressEvent;
      if (event.type === "progress") {
        const phaseOrder = INGESTION_PHASE_ORDER[event.phase];
        const lastPhaseOrder = lastProgress
          ? INGESTION_PHASE_ORDER[lastProgress.phase]
          : -1;
        if (
          phaseOrder < lastPhaseOrder ||
          (phaseOrder === lastPhaseOrder &&
            lastProgress !== null &&
            event.done <= lastProgress.done)
        ) {
          continue;
        }
        lastProgress = event;
        onProgress(event);
      } else if (event.type === "complete") {
        return await claimCompletedUpload(uploadId, signal);
      } else if (event.type === "selection_required") {
        onSelection(event.choices);
      } else if (event.type === "error") {
        throw new UploadIngestionError(event.error_code);
      } else {
        throw new UploadIngestionError("upload_failed");
      }
    }
    if (lastStreamError instanceof Error) throw lastStreamError;
    if (lastStreamError) throw new UploadIngestionError("upload_failed");
  }
  if (!signal.aborted) throw new UploadIngestionError("upload_failed");
  throw new DOMException("Upload cancelled", "AbortError");
}

export function useDirectZipUpload(options: {
  maxFileSize: number;
  onUploaded: (result: UploadResult) => void;
}) {
  const file = ref<File | null>(null);
  const status = ref<UploadState>("idle");
  const progress = ref(0);
  const processingPhase = ref<UploadIngestionPhase | null>(null);
  const errorCode = ref<string | null>(null);
  const choices = ref<TripChoice[]>([]);
  const selectedIds = ref<string[]>([]);
  const selectionSubmitting = ref(false);
  const selectionError = ref(false);
  let uploadId: string | null = null;
  let streamController: AbortController | null = null;
  const pendingController = new AbortController();

  const uppy = new Uppy<UploadMeta, UploadBody>({
    autoProceed: true,
    restrictions: {
      allowedFileTypes: [".zip"],
      maxFileSize: options.maxFileSize,
      maxNumberOfFiles: 1,
    },
  }).use(AwsS3, {
    endpoint: `${window.location.origin}/api/v1/users/uploads`,
    cookiesRule: "same-origin",
    limit: 8,
    shouldUseMultipart: true,
    allowedMetaFields: ["size_bytes"],
    getChunkSize: () => PART_SIZE,
  });

  function clearState() {
    streamController?.abort();
    streamController = null;
    file.value = null;
    status.value = "idle";
    progress.value = 0;
    processingPhase.value = null;
    errorCode.value = null;
    choices.value = [];
    selectedIds.value = [];
    selectionSubmitting.value = false;
    selectionError.value = false;
    uploadId = null;
  }

  function fail(code?: string | null) {
    status.value = "failed";
    errorCode.value = code === "upload_invalid_zip" ? code : "upload_failed";
  }

  async function followIngestion(uploadId: string): Promise<void> {
    streamController = new AbortController();
    try {
      const result = await followUploadIngestion(
        uploadId,
        streamController.signal,
        (event) => {
          status.value = "processing";
          processingPhase.value = event.phase;
          progress.value =
            event.total > 0 ? Math.min(event.done / event.total, 1) : 0;
        },
        (available) => {
          const availableIds = new Set(available.map((choice) => choice.id));
          choices.value = available;
          selectedIds.value = selectedIds.value.filter((id) =>
            availableIds.has(id),
          );
          status.value = "selecting";
        },
      );
      uppy.clear();
      clearState();
      options.onUploaded(result);
    } catch (error) {
      if ((error as Error).name !== "AbortError") {
        fail(error instanceof UploadIngestionError ? error.code : null);
      }
    }
  }

  uppy.on("upload-progress", (_uploadingFile, uploadProgress) => {
    if (uploadProgress.bytesTotal) {
      progress.value = uploadProgress.bytesUploaded / uploadProgress.bytesTotal;
    }
  });
  uppy.on("upload-success", (uploadedFile) => {
    uploadId = (uploadedFile as MultipartFile | undefined)?.s3Multipart
      ?.uploadId ?? null;
    if (!uploadId) {
      fail();
      return;
    }
    status.value = "processing";
    progress.value = 0;
    processingPhase.value = "downloading";
    void followIngestion(uploadId);
  });
  uppy.on("upload-error", () => fail());

  function addFile(selected: File) {
    file.value = selected;
    status.value = "uploading";
    progress.value = 0;
    processingPhase.value = null;
    errorCode.value = null;
    uppy.addFile({
      name: selected.name,
      type: selected.type,
      data: selected,
      meta: { size_bytes: selected.size },
    });
  }

  function cancel() {
    uppy.cancelAll();
    clearState();
  }

  function reset() {
    uppy.clear();
    clearState();
  }

  async function submitSelection() {
    if (!uploadId || selectedIds.value.length === 0) return;
    selectionSubmitting.value = true;
    selectionError.value = false;
    try {
      await selectUploadTrips({
        path: { upload_id: uploadId },
        body: { trip_ids: selectedIds.value },
        throwOnError: true,
      });
      status.value = "processing";
      processingPhase.value = "validating";
      progress.value = 0;
    } catch {
      selectionError.value = true;
    } finally {
      selectionSubmitting.value = false;
    }
  }

  async function resumePendingUpload() {
    try {
      const { data } = await pendingUpload({
        signal: pendingController.signal,
        throwOnError: true,
      });
      if (!data || status.value !== "idle") return;
      uploadId = data.upload_id;
      choices.value = data.choices;
      status.value =
        data.status === "awaiting_selection" ? "selecting" : "processing";
      processingPhase.value = "downloading";
      void followIngestion(uploadId);
    } catch {
      return;
    }
  }

  void resumePendingUpload();

  onScopeDispose(() => {
    pendingController.abort();
    streamController?.abort();
    uppy.destroy();
  });

  return {
    file,
    status,
    progress,
    processingPhase,
    errorCode,
    choices,
    selectedIds,
    selectionSubmitting,
    selectionError,
    addFile,
    cancel,
    reset,
    submitSelection,
  };
}
