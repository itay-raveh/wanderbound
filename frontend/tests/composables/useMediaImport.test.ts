import { readImportStream } from "@/composables/useMediaImport";

function streamFromText(text: string): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text));
      controller.close();
    },
  });
}

function sseBody(events: object[]): string {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
}

describe("readImportStream", () => {
  it("rejects EOF before import_completed", async () => {
    const onProgress = vi.fn();
    const stream = streamFromText(
      sseBody([
        {
          type: "import_in_progress",
          phase: "downloading",
          done: 1,
          total: 0,
        },
      ]),
    );

    await expect(readImportStream(stream, onProgress)).rejects.toThrow(
      "Import connection closed before completion.",
    );
    expect(onProgress).toHaveBeenCalledWith({
      type: "import_in_progress",
      phase: "downloading",
      done: 1,
      total: 0,
    });
  });
});
