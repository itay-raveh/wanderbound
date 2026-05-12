import { ref } from "vue";
import { readImportStream, useMediaImport } from "@/composables/useMediaImport";

const mocks = vi.hoisted(() => ({
  closeSession: vi.fn(),
  pollSession: vi.fn(),
  authorize: vi.fn(),
  invalidateQueries: vi.fn(),
  getQueryData: vi.fn(),
  setQueryData: vi.fn(),
  getConfig: vi.fn(() => ({ baseUrl: "" })),
}));

vi.mock("@/client/client.gen", () => ({
  client: { getConfig: mocks.getConfig },
}));

vi.mock("@pinia/colada", () => ({
  useQueryCache: () => ({
    invalidateQueries: mocks.invalidateQueries,
    getQueryData: mocks.getQueryData,
    setQueryData: mocks.setQueryData,
  }),
}));

vi.mock("@/composables/useGooglePhotos", () => ({
  useGooglePhotos: () => ({
    state: ref("connected"),
    isConnected: ref(true),
    authorize: mocks.authorize,
    pollSession: mocks.pollSession,
    closeSession: mocks.closeSession,
  }),
}));

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

describe("useMediaImport", () => {
  function mockPopup(): Window {
    const popup = {
      closed: false,
      close: vi.fn(),
      location: { href: "" },
      document: {
        title: "",
        body: { style: { cssText: "" }, textContent: "" },
      },
    } as unknown as Window;
    vi.spyOn(window, "open").mockReturnValue(popup);
    return popup;
  }

  function mockImportSessionFetch() {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          session_id: "session-abc",
          picker_uri: "https://photos.google.com/picker/abc",
        }),
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  beforeEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    mocks.closeSession.mockReset();
    mocks.pollSession.mockReset();
    mocks.authorize.mockReset();
    mocks.invalidateQueries.mockReset();
    mocks.getQueryData.mockReset();
    mocks.setQueryData.mockReset();
    mocks.getConfig.mockReturnValue({ baseUrl: "" });
    mocks.closeSession.mockResolvedValue(undefined);
  });

  it("closes a Google Picker session when import fails after session creation", async () => {
    mockPopup();
    mockImportSessionFetch();
    mocks.pollSession.mockRejectedValue(new Error("selection failed"));

    const mediaImport = useMediaImport(() => "aid-1");
    await mediaImport.importGoogle({ context: "cover" });

    expect(mocks.closeSession).toHaveBeenCalledWith("session-abc");
    expect(mediaImport.phase.value).toBe("error");
    expect(mediaImport.errorDetail.value).toBe("selection failed");
  });

  it("stays canceled when Google Picker polling resolves after cancel", async () => {
    mockPopup();
    const fetchMock = mockImportSessionFetch();
    let resolvePoll!: (result: { ready: boolean }) => void;
    mocks.pollSession.mockReturnValue(
      new Promise((resolve) => {
        resolvePoll = resolve;
      }),
    );

    const mediaImport = useMediaImport(() => "aid-1");
    const importPromise = mediaImport.importGoogle({ context: "cover" });
    await vi.waitFor(() =>
      expect(mocks.pollSession).toHaveBeenCalledWith("session-abc"),
    );

    mediaImport.cancel();
    resolvePoll({ ready: true });
    await importPromise;

    expect(mediaImport.phase.value).toBe("idle");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(mocks.closeSession).toHaveBeenCalledWith("session-abc");
  });
});
