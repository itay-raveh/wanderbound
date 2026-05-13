import { readImportStream } from "@/composables/useMediaImport";
import { externalMediaInvalidationKeys } from "@/composables/useAddExternalMedia";
import { queryKeys } from "@/queries/keys";

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

describe("externalMediaInvalidationKeys", () => {
  it("invalidates steps when imported media is added to a step", () => {
    expect(
      externalMediaInvalidationKeys("album-1", {
        context: "step",
        stepId: 1,
      }),
    ).toEqual([
      queryKeys.album("album-1"),
      queryKeys.media("album-1"),
      queryKeys.steps("album-1"),
    ]);
  });

  it("does not invalidate steps for cover imports", () => {
    expect(
      externalMediaInvalidationKeys("album-1", { context: "cover" }),
    ).toEqual([queryKeys.album("album-1"), queryKeys.media("album-1")]);
  });
});
