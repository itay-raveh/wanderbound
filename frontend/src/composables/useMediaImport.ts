import { client } from "@/client/client.gen";
import { useGooglePhotos } from "@/composables/useGooglePhotos";
import { t } from "@/i18n";
import { queryKeys } from "@/queries/keys";
import { sleep } from "@/utils/async";
import type { Step } from "@/client";
import { useQueryCache } from "@pinia/colada";
import { computed, nextTick, ref } from "vue";

type ImportContext = "step" | "cover";
type ImportPhase =
  | "idle"
  | "authorizing"
  | "picking"
  | "uploading"
  | "processing"
  | "done"
  | "error";

interface ImportTarget {
  context: ImportContext;
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

interface ImportFailed {
  type: "import_failed";
  detail: string;
}

interface ImportInProgress {
  type: "import_in_progress";
  phase: string;
  done: number;
  total: number;
}

type ImportEvent = ImportCompleted | ImportFailed | ImportInProgress;

const POLL_INTERVAL_MS = 2000;
const PICKER_TIMEOUT_MS = 10 * 60 * 1000;
const DONE_RESET_MS = 2500;
const MAX_ITEMS = 50;

export function useMediaImport(albumId: () => string) {
  const cache = useQueryCache();
  const googlePhotos = useGooglePhotos();
  const phase = ref<ImportPhase>("idle");
  const progress = ref<ImportProgress>({ done: 0, total: 0 });
  const importedCount = ref(0);
  const errorDetail = ref<string | null>(null);

  let controller: AbortController | null = null;
  let resetTimer: ReturnType<typeof setTimeout> | null = null;
  let activePopup: Window | null = null;

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

  async function invalidateAlbumQueries(target: ImportTarget) {
    const aid = albumId();
    const invalidations = [
      cache.invalidateQueries({ key: queryKeys.album(aid) }),
      cache.invalidateQueries({ key: queryKeys.media(aid) }),
    ];
    if (target.context !== "step") {
      invalidations.push(
        cache.invalidateQueries({ key: queryKeys.steps(aid) }),
      );
    }
    await Promise.all(invalidations);
  }

  function applyImportResult(result: ImportCompleted, target: ImportTarget) {
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
    target: ImportTarget,
    onCompleted?: (result: ImportCompleted) => void,
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
      onCompleted?.(result);
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
    target: ImportTarget,
    signal: AbortSignal,
  ): Promise<ImportCompleted> {
    const form = new FormData();
    form.set("context", target.context);
    if (target.stepId != null) form.set("step_id", String(target.stepId));
    for (const file of files) form.append("files", file);

    const baseUrl = client.getConfig().baseUrl ?? "";
    return fetch(`${baseUrl}/api/v1/albums/${albumId()}/media-imports/device`, {
      method: "POST",
      credentials: "include",
      body: form,
      signal,
    }).then(async (res) => {
      if (!res.ok) throw new Error(statusMessage(res.status));
      return (await res.json()) as ImportCompleted;
    });
  }

  async function importGoogle(
    target: ImportTarget,
    onCompleted?: (result: ImportCompleted) => void,
  ): Promise<ImportCompleted | undefined> {
    if (resetTimer !== null) clearTimeout(resetTimer);
    reset();
    controller = new AbortController();
    const signal = controller.signal;
    let sessionId: string | null = null;

    try {
      activePopup = openPopup();
      if (!googlePhotos.isConnected.value) {
        phase.value = "authorizing";
        await googlePhotos.authorize(activePopup, signal);
      }

      phase.value = "picking";
      const session = await createImportSession(signal);
      sessionId = session.session_id;
      activePopup.location.href = `${session.picker_uri}/autoclose`;
      await pollUntilReady(sessionId, signal);

      phase.value = "processing";
      const result = await runGoogleImportStream(sessionId, target, signal);
      onCompleted?.(result);
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
      if (sessionId) googlePhotos.closeSession(sessionId).catch(() => {});
    }
  }

  async function createImportSession(signal: AbortSignal): Promise<{
    session_id: string;
    picker_uri: string;
  }> {
    const baseUrl = client.getConfig().baseUrl ?? "";
    const res = await fetch(
      `${baseUrl}/api/v1/albums/${albumId()}/media-imports/google/session`,
      { method: "POST", credentials: "include", signal },
    );
    if (!res.ok) throw new Error(statusMessage(res.status));
    return (await res.json()) as { session_id: string; picker_uri: string };
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
    target: ImportTarget,
    signal: AbortSignal,
  ): Promise<ImportCompleted> {
    const baseUrl = client.getConfig().baseUrl ?? "";
    const res = await fetch(
      `${baseUrl}/api/v1/albums/${albumId()}/media-imports/google`,
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

async function* parseSse(stream: ReadableStream<Uint8Array>) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split = buffer.indexOf("\n\n");
    while (split !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) yield JSON.parse(data) as ImportEvent;
      split = buffer.indexOf("\n\n");
    }
  }
}

export async function readImportStream(
  stream: ReadableStream<Uint8Array>,
  onProgress: (event: ImportInProgress) => void,
): Promise<ImportCompleted> {
  let completed: ImportCompleted | null = null;
  for await (const event of parseSse(stream)) {
    if (event.type === "import_in_progress") {
      onProgress(event);
    } else if (event.type === "import_failed") {
      throw new Error(event.detail);
    } else {
      completed = event;
    }
  }
  if (!completed) throw new Error(t("mediaImport.errors.incompleteStream"));
  return completed;
}

function statusMessage(statusCode: number): string {
  if (statusCode === 400) return t("mediaImport.errors.badFile");
  if (statusCode === 403) return t("mediaImport.errors.googleUnavailable");
  if (statusCode === 413) return t("mediaImport.errors.tooLarge");
  return t("mediaImport.error");
}
