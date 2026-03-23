/**
 * Tests for usePdfExportStream state machine and abort behavior.
 */

// Mock the i18n t() function to return predictable strings
vi.mock("@/i18n", () => {
  const t = (key: string, params?: Record<string, string>) => {
    if (key === "pdf.loading") return "Loading album...";
    if (key === "pdf.renderingSingle") return "Rendering...";
    if (key === "pdf.renderingBytes" && params) return `Rendering... ${params.size}`;
    if (key === "pdf.queued") return "Queued...";
    if (key === "error.pdfExport") return "PDF export failed";
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

// Mock the client to avoid real API calls
vi.mock("@/client", () => ({
  generatePdf: vi.fn(),
}));

vi.mock("@/client/client.gen", () => ({
  client: {
    getConfig: () => ({ baseUrl: "http://localhost:8000" }),
  },
}));

import type { PdfStreamState, UsePdfExportStream } from "@/composables/usePdfExportStream";

describe("usePdfExportStream", () => {
  let stream: UsePdfExportStream;

  beforeEach(async () => {
    // Dynamic import to get fresh instance after mocks
    const mod = await import("@/composables/usePdfExportStream");
    stream = mod.usePdfExportStream(() => "test-album-id");
  });

  it("starts in idle state", () => {
    expect(stream.state.value).toBe("idle");
  });

  it("abort resets to idle", () => {
    stream.state.value = "running" as PdfStreamState;
    stream.abort();
    expect(stream.state.value).toBe("idle");
  });

  it("abort from queued resets to idle", () => {
    stream.state.value = "queued" as PdfStreamState;
    stream.abort();
    expect(stream.state.value).toBe("idle");
  });

  it("abort is safe to call multiple times", () => {
    stream.abort();
    stream.abort();
    expect(stream.state.value).toBe("idle");
  });
});
