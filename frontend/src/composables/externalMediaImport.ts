import type { StepRead as Step } from "@/client";
import { client } from "@/client/client.gen";
import { t } from "@/i18n";
import { invalidateAlbumKey, queryKeys } from "@/queries/keys";
import type { EntryKey, useQueryCache } from "@pinia/colada";
import { readImportStream } from "./useMediaImport";

type QueryCache = ReturnType<typeof useQueryCache>;
type ExternalImportContext = "step" | "cover";

export interface ExternalImportTarget {
  context: ExternalImportContext;
  stepId?: number;
}

export interface ImportCompleted {
  type: "import_completed";
  names: string[];
}

export function applyImportResult(
  cache: QueryCache,
  albumId: string,
  result: ImportCompleted,
  target: ExternalImportTarget,
) {
  if (target.context !== "step" || target.stepId == null) return;
  const key = queryKeys.steps(albumId);
  const steps = cache.getQueryData<Step[]>(key);
  if (!steps) return;
  const imported = result.names.filter((name) =>
    steps.every((step) => !step.unused.includes(name)),
  );
  if (imported.length === 0) return;
  cache.setQueryData(
    key,
    steps.map((step) =>
      step.id === target.stepId
        ? { ...step, unused: [...imported, ...step.unused] }
        : step,
    ),
  );
}

export async function invalidateExternalMediaQueries(
  cache: QueryCache,
  albumId: string,
  target: ExternalImportTarget,
) {
  const keys: EntryKey[] = [
    queryKeys.album(albumId),
    queryKeys.media(albumId),
  ];
  if (target.context === "step") keys.push(queryKeys.steps(albumId));
  await Promise.all(
    [...keys, queryKeys.printBundles(albumId)].map((key) =>
      cache.invalidateQueries(invalidateAlbumKey(key)),
    ),
  );
}

export async function uploadDeviceFiles(
  albumId: string,
  files: File[],
  target: ExternalImportTarget,
  signal: AbortSignal,
): Promise<ImportCompleted> {
  const form = new FormData();
  form.set("context", target.context);
  if (target.stepId != null) form.set("step_id", String(target.stepId));
  for (const file of files) form.append("files", file);

  const response = await fetch(
    `${client.getConfig().baseUrl ?? ""}/api/v1/albums/${albumId}/external-media/add/device`,
    {
      method: "POST",
      credentials: "include",
      body: form,
      signal,
    },
  );
  if (!response.ok) throw new Error(importStatusMessage(response.status));
  return (await response.json()) as ImportCompleted;
}

export async function runGoogleImportStream(
  albumId: string,
  sessionId: string,
  target: ExternalImportTarget,
  signal: AbortSignal,
  onProgress: (done: number, total: number) => void,
): Promise<ImportCompleted> {
  const response = await fetch(
    `${client.getConfig().baseUrl ?? ""}/api/v1/albums/${albumId}/external-media/add/google`,
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
  if (!response.ok || !response.body) {
    throw new Error(importStatusMessage(response.status));
  }
  return readImportStream(response.body, (event) =>
    onProgress(event.done, event.total),
  );
}

function importStatusMessage(statusCode: number): string {
  if (statusCode === 400) return t("mediaImport.errors.badFile");
  if (statusCode === 403) return t("mediaImport.errors.googleUnavailable");
  if (statusCode === 413) return t("mediaImport.errors.tooLarge");
  return t("mediaImport.error");
}
