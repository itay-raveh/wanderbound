import { client } from "@/client/client.gen";
import { useAlbum } from "@/composables/useAlbum";
import { useGooglePhotos } from "@/composables/useGooglePhotos";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { t } from "@/i18n";
import { invalidateAlbumKey, queryKeys } from "@/queries/keys";
import { useQueryCache } from "@pinia/colada";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { sleep } from "@/utils/async";
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

export interface ReplacementReviewState {
  mediaName: string;
  current: {
    kind: "photo" | "video";
    width: number;
    height: number;
    previewUrl: string;
  };
  replacement: PreviewInfo;
  warnings: string[];
  blockedReason: string | null;
}

const POLL_INTERVAL_MS = 2000;
const PICKER_TIMEOUT_MS = 10 * 60 * 1000;

export function useReplaceExternalMedia() {
  const { t: translate } = useI18n();
  const { albumId, mediaByName } = useAlbum();
  const cache = useQueryCache();
  const googlePhotos = useGooglePhotos();
  const photoFocus = usePhotoFocus();

  const phase = ref<ReplacePhase>("idle");
  const errorDetail = ref<string | null>(null);
  const review = ref<ReplacementReviewState | null>(null);

  let controller: AbortController | null = null;
  let activePopup: Window | null = null;
  let activeSessionId: string | null = null;

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
    ["authorizing", "picking", "replacing"].includes(phase.value),
  );

  function setError(message: string) {
    phase.value = "error";
    errorDetail.value = message;
  }

  function cleanupReview() {
    if (review.value) URL.revokeObjectURL(review.value.replacement.previewUrl);
    review.value = null;
  }

  function reset() {
    controller?.abort();
    controller = null;
    errorDetail.value = null;
    cleanupReview();
    try {
      activePopup?.close();
    } catch {
      /* Cross-origin opener policy can block this. */
    }
    activePopup = null;
    if (activeSessionId)
      googlePhotos.closeSession(activeSessionId).catch(() => {});
    activeSessionId = null;
  }

  function openPopup(): Window {
    const width = Math.min(screen.availWidth - 100, 1200);
    const height = Math.min(screen.availHeight - 100, 900);
    const left =
      ((screen as { availLeft?: number }).availLeft ?? 0) +
      (screen.availWidth - width) / 2;
    const top =
      ((screen as { availTop?: number }).availTop ?? 0) +
      (screen.availHeight - height) / 2;
    const popup = window.open(
      "about:blank",
      "google-photos",
      `width=${width},height=${height},left=${left},top=${top}`,
    );
    if (!popup) throw new Error(t("mediaImport.errors.popupBlocked"));
    popup.document.title = "Google Photos";
    popup.document.body.style.cssText =
      "font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0;color:#666";
    popup.document.body.textContent = translate("mediaImport.authorizing");
    return popup;
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
    errorDetail.value = null;

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
      phase.value = "review";
      return review.value;
    } catch {
      setError(translate("externalMedia.review.errors.previewFailed"));
      return null;
    }
  }

  async function confirmDeviceReplacement(): Promise<string | null> {
    const currentReview = review.value;
    if (!currentReview) return null;
    if (currentReview.blockedReason) {
      setError(currentReview.blockedReason);
      return null;
    }
    controller = new AbortController();
    phase.value = "replacing";
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
          signal: controller.signal,
        },
      );
      if (!res.ok) throw new Error(statusMessage(res.status));
      await invalidateQueries();
      phase.value = "done";
      const name = currentReview.mediaName;
      cleanupReview();
      phase.value = "idle";
      return name;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return null;
      setError(
        err instanceof Error
          ? err.message
          : translate("externalMedia.replace.error"),
      );
      return null;
    }
  }

  async function replaceFromGoogle(): Promise<string | null> {
    const mediaName = selectedMediaName.value;
    if (!mediaName) {
      setError(translate("externalMedia.replace.noSelection"));
      return null;
    }
    controller = new AbortController();
    const signal = controller.signal;
    errorDetail.value = null;
    try {
      activePopup = openPopup();
      if (!googlePhotos.isConnected.value) {
        phase.value = "authorizing";
        await googlePhotos.authorize(activePopup, signal);
      }
      phase.value = "picking";
      const session = await googlePhotos.createPickerSession(
        activePopup,
        signal,
        { maxItemCount: GOOGLE_REPLACEMENT_MAX_ITEMS },
      );
      activeSessionId = session.sessionId;
      activePopup.location.href = `${session.pickerUri}/autoclose`;
      await pollUntilReady(session.sessionId, signal);

      phase.value = "replacing";
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
            session_id: session.sessionId,
          }),
        },
      );
      if (!res.ok) throw new Error(statusMessage(res.status));
      await invalidateQueries();
      phase.value = "done";
      phase.value = "idle";
      return mediaName;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return null;
      setError(
        err instanceof Error
          ? err.message
          : translate("externalMedia.replace.error"),
      );
      return null;
    } finally {
      try {
        activePopup?.close();
      } catch {
        /* Cross-origin opener policy can block this. */
      }
      activePopup = null;
      if (activeSessionId)
        googlePhotos.closeSession(activeSessionId).catch(() => {});
      activeSessionId = null;
    }
  }

  async function invalidateQueries() {
    await Promise.all(
      replacementInvalidationKeys(albumId.value).map((key) =>
        cache.invalidateQueries(invalidateAlbumKey(key)),
      ),
    );
  }

  async function pollUntilReady(
    sessionId: string,
    signal: AbortSignal,
  ): Promise<void> {
    const deadline = Date.now() + PICKER_TIMEOUT_MS;
    while (!signal.aborted) {
      if (Date.now() > deadline) {
        throw new Error(translate("mediaImport.errors.selectionTimeout"));
      }
      const result = await googlePhotos.pollSession(sessionId);
      signal.throwIfAborted();
      if (result.ready) return;
      await sleep(POLL_INTERVAL_MS, signal);
    }
  }

  function cancelReview() {
    cleanupReview();
    if (phase.value === "review") phase.value = "idle";
  }

  function cancel() {
    phase.value = "idle";
    reset();
  }

  return {
    phase,
    errorDetail,
    review,
    isBusy,
    googlePhotosState: googlePhotos.state,
    selectedMedia,
    selectedMediaName,
    prepareDeviceReview,
    confirmDeviceReplacement,
    replaceFromGoogle,
    cancelReview,
    cancel,
  };
}

export function replacementInvalidationKeys(aid: string) {
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
