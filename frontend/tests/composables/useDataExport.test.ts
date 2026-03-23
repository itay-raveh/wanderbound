vi.mock("@/i18n", () => {
  const t = (key: string, params?: Record<string, unknown>) => {
    if (key === "export.preparing") return "Preparing export...";
    if (key === "export.progress" && params) return `Exporting... ${String(params.done)} / ${String(params.total)}`;
    if (key === "error.dataExport") return "Data export failed. Please try again.";
    return key;
  };
  return {
    default: {
      global: { locale: { value: "en" }, t },
      install: vi.fn(),
    },
    t,
  };
});

vi.mock("@/client", () => ({
  exportData: vi.fn(),
}));

vi.mock("@/client/client.gen", () => ({
  client: {
    getConfig: () => ({ baseUrl: "http://localhost:8000" }),
  },
}));

import type { SseDownloadHandle, SseStreamState } from "@/composables/useSseDownload";

describe("useDataExport", () => {
  let stream: SseDownloadHandle;

  beforeEach(async () => {
    const mod = await import("@/composables/useDataExport");
    stream = mod.useDataExport();
  });

  it("starts in idle state", () => {
    expect(stream.state.value).toBe("idle");
  });

  it("abort resets to idle", () => {
    stream.state.value = "running" as SseStreamState;
    stream.abort();
    expect(stream.state.value).toBe("idle");
  });

  it("abort is safe to call multiple times", () => {
    stream.abort();
    stream.abort();
    expect(stream.state.value).toBe("idle");
  });
});
