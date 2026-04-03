vi.mock("@/i18n", () => {
  const t = (key: string, params?: Record<string, string>) => {
    if (key === "pdf.loading") return "Loading album...";
    if (key === "pdf.renderingSingle") return "Generating PDF...";
    if (key === "pdf.renderingBytes" && params) return `Generating PDF... ${params.size}`;
    if (key === "pdf.queued") return "Waiting to start...";
    if (key === "error.pdfExport") return "PDF export failed. Please try again.";
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
  generatePdf: vi.fn(),
}));

vi.mock("@/client/client.gen", () => ({
  client: {
    getConfig: () => ({ baseUrl: "http://localhost:8000" }),
  },
}));

import type { SseDownloadHandle, SseStreamState } from "@/composables/useSseDownload";

describe("usePdfExportStream", () => {
  let stream: SseDownloadHandle;

  beforeEach(async () => {
    const mod = await import("@/composables/usePdfExportStream");
    stream = mod.usePdfExportStream(() => "test-album-id");
  });

  it("starts in idle state", () => {
    expect(stream.state.value).toBe("idle");
  });

  it("abort resets to idle", () => {
    stream.state.value = "running" as SseStreamState;
    stream.abort();
    expect(stream.state.value).toBe("idle");
  });

});
