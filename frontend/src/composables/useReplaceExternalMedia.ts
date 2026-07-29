import { client } from "@/client/client.gen";
import type { AlbumMedia } from "@/client";
import { useAlbum } from "@/composables/useAlbum";
import { useGooglePhotos } from "@/composables/useGooglePhotos";
import { useGooglePhotosPicker } from "@/composables/useGooglePhotosPicker";
import { useMediaOperationState } from "@/composables/useMediaOperationState";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { t } from "@/i18n";
import { invalidateAlbumKey, queryKeys } from "@/queries/keys";
import { useQueryCache } from "@pinia/colada";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { GOOGLE_REPLACEMENT_MAX_ITEMS } from "@/utils/externalMediaLimits";
import { isVideo, mediaUrl, posterPath } from "@/utils/media";

type ReplacePhase =
  | "idle"
  | "authorizing"
  | "picking"
  | "review"
  | "replacing"
  | "done"
  | "error";

interface PreviewInfo {
  file: File;
  kind: "photo" | "video";
  width: number;
  height: number;
  previewUrl: string;
}

type MediaDimensions = { width: number; height: number };

export interface ReplacementMetadata extends MediaDimensions {
  byteSize: number;
}

export interface ReplacementResult {
  mediaName: string;
  previous: ReplacementMetadata;
  replacement: ReplacementMetadata;
}

export interface ReplacementReviewState {
  mediaName: string;
  current: {
    kind: "photo" | "video";
    width: number;
    height: number;
    byteSize: number;
    previewUrl: string;
  };
  replacement: PreviewInfo;
  warnings: string[];
  blockedReason: string | null;
}

export function useReplaceExternalMedia() {
  const { t: translate } = useI18n();
  const { albumId, mediaByName } = useAlbum();
  const cache = useQueryCache();
  const googlePhotos = useGooglePhotos();
  const operation = useMediaOperationState<ReplacePhase>("idle", "error");
  const picker = useGooglePhotosPicker(googlePhotos, {
    blocked: t("mediaImport.errors.popupBlocked"),
    loading: translate("mediaImport.authorizing"),
    timeout: translate("mediaImport.errors.selectionTimeout"),
  });
  const photoFocus = usePhotoFocus();

  const review = ref<ReplacementReviewState | null>(null);

  const selectedMediaName = computed(() => photoFocus.focusedPhotoId.value);
  const selectedMedia = computed(() =>
    selectedMediaName.value
      ? (mediaByName.value.get(selectedMediaName.value) ?? null)
      : null,
  );
  const selectedKind = computed<"photo" | "video" | null>(() => {
    if (!selectedMediaName.value) return null;
    return isVideo(selectedMediaName.value) ? "video" : "photo";
  });
  const isBusy = computed(() =>
    ["authorizing", "picking", "replacing"].includes(operation.phase.value),
  );

  function setError(message: string) {
    operation.setError(message);
  }

  function cleanupReview() {
    if (review.value) URL.revokeObjectURL(review.value.replacement.previewUrl);
    review.value = null;
  }

  function reset() {
    operation.abort();
    operation.clearError();
    cleanupReview();
    picker.cleanup();
  }

  async function prepareDeviceReview(
    file: File,
  ): Promise<ReplacementReviewState | null> {
    if (
      !selectedMediaName.value ||
      !selectedMedia.value ||
      !selectedKind.value
    ) {
      setError(translate("externalMedia.replace.noSelection"));
      return null;
    }
    cleanupReview();
    operation.clearError();

    try {
      const replacement = await readPreviewInfo(file);
      const warnings = buildWarnings(selectedMedia.value, replacement);
      const blockedReason =
        replacement.kind !== selectedKind.value
          ? translate("externalMedia.review.errors.typeMismatch")
          : null;
      review.value = {
        mediaName: selectedMediaName.value,
        current: {
          kind: selectedKind.value,
          width: selectedMedia.value.width,
          height: selectedMedia.value.height,
          byteSize: selectedMedia.value.byte_size,
          previewUrl: currentPreviewUrl(
            albumId.value,
            selectedMediaName.value,
            selectedKind.value,
            selectedMedia.value.updated_at,
          ),
        },
        replacement,
        warnings,
        blockedReason,
      };
      operation.phase.value = "review";
      return review.value;
    } catch {
      setError(translate("externalMedia.review.errors.previewFailed"));
      return null;
    }
  }

  async function confirmDeviceReplacement(): Promise<ReplacementResult | null> {
    const currentReview = review.value;
    if (!currentReview) return null;
    if (currentReview.blockedReason) {
      setError(currentReview.blockedReason);
      return null;
    }
    const signal = operation.begin();
    operation.phase.value = "replacing";
    try {
      const form = new FormData();
      form.set("media_name", currentReview.mediaName);
      form.set("file", currentReview.replacement.file);
      const baseUrl = client.getConfig().baseUrl ?? "";
      const res = await fetch(
        `${baseUrl}/api/v1/albums/${albumId.value}/external-media/replace/device`,
        {
          method: "POST",
          credentials: "include",
          body: form,
          signal,
        },
      );
      if (!res.ok) throw new Error(statusMessage(res.status));
      const replacement = (await res.json()) as AlbumMedia;
      await invalidateQueries();
      operation.phase.value = "done";
      const result = replacementResult(
        currentReview.mediaName,
        currentReview.current,
        replacement,
      );
      cleanupReview();
      operation.phase.value = "idle";
      return result;
    } catch (err) {
      operation.fail(err, translate("externalMedia.replace.error"));
      return null;
    }
  }

  async function replaceFromGoogle(
    onRequestStart?: () => void,
  ): Promise<ReplacementResult | null> {
    const mediaName = selectedMediaName.value;
    const previous = selectedMedia.value;
    if (!mediaName || !previous) {
      setError(translate("externalMedia.replace.noSelection"));
      return null;
    }
    const signal = operation.begin();
    try {
      picker.open();
      if (!picker.isConnected.value) {
        operation.phase.value = "authorizing";
        await picker.authorize(signal);
      }
      operation.phase.value = "picking";
      const sessionId = await picker.pick(signal, {
        maxItemCount: GOOGLE_REPLACEMENT_MAX_ITEMS,
        checkAbortedAfterPoll: true,
      });

      operation.phase.value = "replacing";
      onRequestStart?.();
      const baseUrl = client.getConfig().baseUrl ?? "";
      const res = await fetch(
        `${baseUrl}/api/v1/albums/${albumId.value}/external-media/replace/google`,
        {
          method: "POST",
          credentials: "include",
          signal,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            media_name: mediaName,
            session_id: sessionId,
          }),
        },
      );
      if (!res.ok) throw new Error(statusMessage(res.status));
      const replacement = (await res.json()) as AlbumMedia;
      await invalidateQueries();
      operation.phase.value = "done";
      operation.phase.value = "idle";
      return replacementResult(
        mediaName,
        albumMediaMetadata(previous),
        replacement,
      );
    } catch (err) {
      operation.fail(err, translate("externalMedia.replace.error"));
      return null;
    } finally {
      picker.cleanup();
    }
  }

  async function invalidateQueries() {
    await Promise.all(
      replacementInvalidationKeys(albumId.value).map((key) =>
        cache.invalidateQueries(invalidateAlbumKey(key)),
      ),
    );
  }

  function cancelReview() {
    cleanupReview();
    if (operation.phase.value === "review") operation.phase.value = "idle";
  }

  function cancel() {
    operation.cancel();
    reset();
  }

  return {
    phase: operation.phase,
    errorDetail: operation.errorDetail,
    review,
    isBusy,
    googlePhotosState: picker.state,
    selectedMedia,
    selectedMediaName,
    prepareDeviceReview,
    confirmDeviceReplacement,
    replaceFromGoogle,
    cancelReview,
    cancel,
  };
}

function replacementInvalidationKeys(aid: string) {
  return [
    queryKeys.album(aid),
    queryKeys.media(aid),
    queryKeys.steps(aid),
    queryKeys.printBundles(aid),
  ];
}

function currentPreviewUrl(
  aid: string,
  mediaName: string,
  kind: "photo" | "video",
  updatedAt: string | undefined,
): string {
  const base = mediaUrl(
    kind === "video" ? posterPath(mediaName) : mediaName,
    aid,
  );
  return updatedAt ? `${base}?d=${encodeURIComponent(updatedAt)}` : base;
}

function buildWarnings(
  media: MediaDimensions,
  replacement: PreviewInfo,
): string[] {
  const warnings: string[] = [];
  if (replacement.width * replacement.height < media.width * media.height) {
    warnings.push(t("externalMedia.review.warnings.lowerResolution"));
  }
  const currentAspect = media.width / media.height;
  const replacementAspect = replacement.width / replacement.height;
  if (Math.abs(currentAspect - replacementAspect) / currentAspect > 0.15) {
    warnings.push(t("externalMedia.review.warnings.aspectRatio"));
  }
  const currentPortrait = media.height > media.width;
  const replacementPortrait = replacement.height > replacement.width;
  if (currentPortrait !== replacementPortrait) {
    warnings.push(t("externalMedia.review.warnings.orientation"));
  }
  return warnings;
}

async function readPreviewInfo(file: File): Promise<PreviewInfo> {
  const previewUrl = URL.createObjectURL(file);
  const kind = file.type.startsWith("video/") ? "video" : "photo";
  try {
    const size =
      kind === "video"
        ? await readVideoSize(previewUrl)
        : await readImageSize(previewUrl);
    return { file, kind, previewUrl, ...size };
  } catch (error) {
    URL.revokeObjectURL(previewUrl);
    throw error;
  }
}

function readImageSize(
  src: string,
): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () =>
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => reject(new Error("preview failed"));
    img.src = src;
  });
}

function readVideoSize(
  src: string,
): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () =>
      resolve({ width: video.videoWidth, height: video.videoHeight });
    video.onerror = () => reject(new Error("preview failed"));
    video.src = src;
  });
}

function statusMessage(statusCode: number): string {
  if (statusCode === 400) return t("externalMedia.replace.invalid");
  if (statusCode === 403) return t("mediaImport.errors.googleUnavailable");
  if (statusCode === 413) return t("mediaImport.errors.tooLarge");
  return t("externalMedia.replace.error");
}

function replacementResult(
  mediaName: string,
  previous: ReplacementMetadata,
  replacement: AlbumMedia,
): ReplacementResult {
  return {
    mediaName,
    previous: {
      width: previous.width,
      height: previous.height,
      byteSize: previous.byteSize,
    },
    replacement: albumMediaMetadata(replacement),
  };
}

function albumMediaMetadata(media: AlbumMedia): ReplacementMetadata {
  return {
    width: media.width,
    height: media.height,
    byteSize: media.byte_size,
  };
}
