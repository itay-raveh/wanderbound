import { t } from "@/i18n";

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
