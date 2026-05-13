import type { StepRead as Step } from "@/client";
import { client } from "@/client/client.gen";
import { useGooglePhotos } from "@/composables/useGooglePhotos";
import { t } from "@/i18n";
import { queryKeys } from "@/queries/keys";
import { sleep } from "@/utils/async";
import { useQueryCache } from "@pinia/colada";
import { computed, nextTick, ref } from "vue";
import { readImportStream } from "./useMediaImport";

export type ExternalImportContext = "step" | "cover";
type AddPhase =
  | "idle"
  | "authorizing"
  | "picking"
  | "uploading"
  | "processing"
  | "done"
  | "error";

export interface ExternalImportTarget {
  context: ExternalImportContext;
  stepId?: number;
}

interface ImportProgress {
  done: number;
  total: number;
}

interface ImportCompleted {
  type: "import_completed";
  names: string[];
}

const POLL_INTERVAL_MS = 2000;
const PICKER_TIMEOUT_MS = 10 * 60 * 1000;
const DONE_RESET_MS = 2500;
const MAX_ITEMS = 50;

export function useAddExternalMedia(albumId: () => string) {
  const cache = useQueryCache();
  const googlePhotos = useGooglePhotos();
  const phase = ref<AddPhase>("idle");
  const progress = ref<ImportProgress>({ done: 0, total: 0 });
  const importedCount = ref(0);
  const errorDetail = ref<string | null>(null);

  let controller: AbortController | null = null;
  let resetTimer: ReturnType<typeof setTimeout> | null = null;
  let activePopup: Window | null = null;
  let activeSessionId: string | null = null;

  const isBusy = computed(() =>
    ["authorizing", "picking", "uploading", "processing"].includes(phase.value),
  );

  function reset() {
    controller?.abort();
    controller = null;
    progress.value = { done: 0, total: 0 };
    importedCount.value = 0;
    errorDetail.value = null;
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
    popup.document.body.textContent = t("mediaImport.authorizing");
    return popup;
  }

  async function invalidateAlbumQueries(target: ExternalImportTarget) {
    const aid = albumId();
    await Promise.all(
      externalMediaInvalidationKeys(aid, target).map((key) =>
        cache.invalidateQueries({ key, exact: true }),
      ),
    );
  }

  function applyImportResult(
    result: ImportCompleted,
    target: ExternalImportTarget,
  ) {
    if (target.context !== "step" || target.stepId == null) return;
    const key = queryKeys.steps(albumId());
    const steps = cache.getQueryData<Step[]>(key);
    if (!steps) return;
    const imported = result.names.filter((name) =>
      steps.every((step) => !step.unused.includes(name)),
    );
    if (imported.length === 0) return;
    const next = steps.map((step) =>
      step.id === target.stepId
        ? { ...step, unused: [...imported, ...step.unused] }
        : step,
    );
    cache.setQueryData(key, next);
  }

  function finish(count: number) {
    importedCount.value = count;
    phase.value = "done";
    resetTimer = setTimeout(() => {
      phase.value = "idle";
      reset();
      resetTimer = null;
    }, DONE_RESET_MS);
  }

  function fail(err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    phase.value = "error";
    errorDetail.value =
      err instanceof Error ? err.message : t("mediaImport.error");
  }

  async function importDevice(
    files: FileList | File[],
    target: ExternalImportTarget,
  ): Promise<ImportCompleted | undefined> {
    const selected = Array.from(files);
    if (selected.length === 0) return;
    if (selected.length > MAX_ITEMS) {
      phase.value = "error";
      errorDetail.value = t("mediaImport.errors.tooMany");
      return;
    }

    if (resetTimer !== null) clearTimeout(resetTimer);
    reset();
    phase.value = "uploading";
    progress.value = { done: 0, total: 1 };
    controller = new AbortController();

    try {
      const result = await uploadDeviceFiles(
        selected,
        target,
        controller.signal,
      );
      phase.value = "processing";
      applyImportResult(result, target);
      await nextTick();
      await invalidateAlbumQueries(target);
      finish(result.names.length);
      return result;
    } catch (err) {
      fail(err);
    }
  }

  function uploadDeviceFiles(
    files: File[],
    target: ExternalImportTarget,
    signal: AbortSignal,
  ): Promise<ImportCompleted> {
    const form = new FormData();
    form.set("context", target.context);
    if (target.stepId != null) form.set("step_id", String(target.stepId));
    for (const file of files) form.append("files", file);

    const baseUrl = client.getConfig().baseUrl ?? "";
    return fetch(
      `${baseUrl}/api/v1/albums/${albumId()}/external-media/add/device`,
      {
        method: "POST",
        credentials: "include",
        body: form,
        signal,
      },
    ).then(async (res) => {
      if (!res.ok) throw new Error(statusMessage(res.status));
      return (await res.json()) as ImportCompleted;
    });
  }

  async function importGoogle(
    target: ExternalImportTarget,
  ): Promise<ImportCompleted | undefined> {
    if (resetTimer !== null) clearTimeout(resetTimer);
    reset();
    controller = new AbortController();
    const signal = controller.signal;

    try {
      activePopup = openPopup();
      if (!googlePhotos.isConnected.value) {
        phase.value = "authorizing";
        await googlePhotos.authorize(activePopup, signal);
      }

      phase.value = "picking";
      const session = await googlePhotos.createPickerSession();
      activeSessionId = session.sessionId;
      activePopup.location.href = `${session.pickerUri}/autoclose`;
      await pollUntilReady(session.sessionId, signal);

      phase.value = "processing";
      const result = await runGoogleImportStream(
        session.sessionId,
        target,
        signal,
      );
      applyImportResult(result, target);
      await nextTick();
      await invalidateAlbumQueries(target);
      finish(result.names.length);
      return result;
    } catch (err) {
      fail(err);
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

  async function pollUntilReady(
    sessionId: string,
    signal: AbortSignal,
  ): Promise<void> {
    const deadline = Date.now() + PICKER_TIMEOUT_MS;
    while (!signal.aborted) {
      if (Date.now() > deadline)
        throw new Error(t("mediaImport.errors.selectionTimeout"));
      const result = await googlePhotos.pollSession(sessionId);
      signal.throwIfAborted();
      if (result.ready) return;
      await sleep(POLL_INTERVAL_MS, signal);
    }
  }

  async function runGoogleImportStream(
    sessionId: string,
    target: ExternalImportTarget,
    signal: AbortSignal,
  ): Promise<ImportCompleted> {
    const baseUrl = client.getConfig().baseUrl ?? "";
    const res = await fetch(
      `${baseUrl}/api/v1/albums/${albumId()}/external-media/add/google`,
      {
        method: "POST",
        credentials: "include",
        signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          context: target.context,
          step_id: target.stepId,
          session_id: sessionId,
        }),
      },
    );
    if (!res.ok || !res.body) throw new Error(statusMessage(res.status));

    return readImportStream(res.body, (event) => {
      progress.value = { done: event.done, total: event.total };
    });
  }

  function cancel() {
    phase.value = "idle";
    reset();
  }

  return {
    phase,
    progress,
    importedCount,
    errorDetail,
    isBusy,
    googlePhotosState: googlePhotos.state,
    importDevice,
    importGoogle,
    cancel,
  };
}

export function externalMediaInvalidationKeys(
  aid: string,
  target: ExternalImportTarget,
) {
  const keys: Array<
    | ReturnType<typeof queryKeys.album>
    | ReturnType<typeof queryKeys.media>
    | ReturnType<typeof queryKeys.steps>
  > = [queryKeys.album(aid), queryKeys.media(aid)];
  if (target.context === "step") keys.push(queryKeys.steps(aid));
  return keys;
}

function statusMessage(statusCode: number): string {
  if (statusCode === 400) return t("mediaImport.errors.badFile");
  if (statusCode === 403) return t("mediaImport.errors.googleUnavailable");
  if (statusCode === 413) return t("mediaImport.errors.tooLarge");
  return t("mediaImport.error");
}
