import type { UploadResult } from "@/client";
import { client } from "@/client/client.gen";
import AwsS3 from "@uppy/aws-s3";
import Uppy, { type UppyFile } from "@uppy/core";
import { onScopeDispose, ref } from "vue";

const PART_SIZE = 64 * 1024 * 1024;
const STATUS_POLL_INTERVAL = 2_000;

type UploadState = "idle" | "uploading" | "processing" | "failed";
type UploadMeta = { size_bytes?: number };
type UploadBody = Record<string, unknown>;
type MultipartFile = UppyFile<UploadMeta, UploadBody> & {
  s3Multipart?: { uploadId?: string };
};

interface StatusResponse {
  status: "processing" | "succeeded" | "failed";
  error_code: string | null;
  result: UploadResult | null;
}

export function useDirectZipUpload(options: {
  maxFileSize: number;
  onUploaded: (result: UploadResult) => void;
}) {
  const file = ref<File | null>(null);
  const status = ref<UploadState>("idle");
  const progress = ref(0);
  const errorCode = ref<string | null>(null);
  let pollTimer: ReturnType<typeof setTimeout> | undefined;

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
    shouldUseMultipart: true,
    allowedMetaFields: ["size_bytes"],
    getChunkSize: () => PART_SIZE,
  });

  function clearState() {
    clearTimeout(pollTimer);
    pollTimer = undefined;
    file.value = null;
    status.value = "idle";
    progress.value = 0;
    errorCode.value = null;
  }

  function fail(code?: string | null) {
    status.value = "failed";
    errorCode.value = code === "upload_invalid_zip" ? code : "upload_failed";
  }

  async function poll(uploadId: string): Promise<void> {
    try {
      const response = await fetch(
        `${client.getConfig().baseUrl}/api/v1/users/uploads/${encodeURIComponent(uploadId)}`,
        { credentials: "include" },
      );
      if (!response.ok) throw new Error("upload status unavailable");
      const body = (await response.json()) as StatusResponse;
      if (body.status === "succeeded" && body.result) {
        uppy.clear();
        clearState();
        options.onUploaded(body.result);
        return;
      }
      if (body.status === "failed") {
        fail(body.error_code);
        return;
      }
    } catch {
      // A later poll can recover from a transient API failure.
    }
    pollTimer = setTimeout(() => void poll(uploadId), STATUS_POLL_INTERVAL);
  }

  uppy.on("upload-progress", (_uploadingFile, uploadProgress) => {
    if (uploadProgress.bytesTotal) {
      progress.value = uploadProgress.bytesUploaded / uploadProgress.bytesTotal;
    }
  });
  uppy.on("upload-success", (uploadedFile) => {
    const uploadId = (uploadedFile as MultipartFile | undefined)?.s3Multipart
      ?.uploadId;
    if (!uploadId) {
      fail();
      return;
    }
    status.value = "processing";
    progress.value = 1;
    void poll(uploadId);
  });
  uppy.on("upload-error", () => fail());

  function addFile(selected: File) {
    file.value = selected;
    status.value = "uploading";
    progress.value = 0;
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

  onScopeDispose(() => {
    clearTimeout(pollTimer);
    uppy.destroy();
  });

  return { file, status, progress, errorCode, addFile, cancel, reset };
}
