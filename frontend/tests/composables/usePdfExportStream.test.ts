import { flushPromises } from "@vue/test-utils";
import { withSetup } from "../helpers";
import { generatePdf } from "@/client";
import { usePdfExportStream } from "@/composables/usePdfExportStream";

const { notifyCreate } = vi.hoisted(() => ({ notifyCreate: vi.fn() }));

vi.mock("quasar", async (importOriginal) => ({
  ...(await importOriginal<typeof import("quasar")>()),
  Notify: { create: notifyCreate },
}));

vi.mock("@/client", () => ({
  generateChaptersPdf: vi.fn(),
  generatePdf: vi.fn(),
}));

vi.mock("@/client/client.gen", () => ({
  client: {
    getConfig: () => ({ baseUrl: "" }),
    setConfig: vi.fn(),
  },
}));

const mockedGeneratePdf = vi.mocked(generatePdf);

describe("usePdfExportStream", () => {
  test("explains queueing and returns to idle when high load persists", async () => {
    let finishWaiting!: () => void;
    const waiting = new Promise<void>((resolve) => {
      finishWaiting = resolve;
    });

    async function* stream() {
      yield { type: "queued" as const };
      await waiting;
      yield { type: "busy" as const };
    }

    mockedGeneratePdf.mockResolvedValue({ stream: stream() } as Awaited<
      ReturnType<typeof generatePdf>
    >);
    const pdf = withSetup(() => usePdfExportStream(() => "trip-1"));

    pdf.start();
    await flushPromises();

    expect(pdf.state.value).toBe("running");
    expect(pdf.progress.value.message).toBe(
      "Waiting for an available PDF worker. During high demand, this can take up to one minute...",
    );

    finishWaiting();
    await flushPromises();

    expect(pdf.state.value).toBe("idle");
    expect(notifyCreate).toHaveBeenCalledWith({
      type: "info",
      message:
        "Your export wasn't started because demand is high. Nothing went wrong. Please try again.",
    });
  });
});
