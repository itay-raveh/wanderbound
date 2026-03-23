/**
 * Tests for useProcessingStream: PHASE_ORDER, initial state, and abort behavior.
 */

// Mock the i18n t() function
vi.mock("@/i18n", () => {
  const t = (key: string) => {
    if (key === "error.processingFailed") return "Processing failed. Please try again later.";
    if (key === "error.connectionFailed") return "Connection failed. Please try again.";
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
vi.mock("@/client", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/client")>();
  return {
    ...orig,
    processUser: vi.fn(),
  };
});

import {
  useProcessingStream,
  PHASE_ORDER,
  type UseProcessingStream,
} from "@/composables/useProcessingStream";

describe("PHASE_ORDER", () => {
  it("contains all three processing phases in order", () => {
    expect(PHASE_ORDER).toEqual(["elevations", "weather", "layouts"]);
  });

  it("has exactly 3 phases", () => {
    expect(PHASE_ORDER).toHaveLength(3);
  });
});

describe("useProcessingStream initial state", () => {
  let stream: UseProcessingStream;

  beforeEach(() => {
    stream = useProcessingStream();
  });

  it("starts in idle state", () => {
    expect(stream.state.value).toBe("idle");
  });

  it("starts with tripIndex at 0", () => {
    expect(stream.tripIndex.value).toBe(0);
  });

  it("starts with null errorDetail", () => {
    expect(stream.errorDetail.value).toBeNull();
  });

  it("starts with zeroed phaseDone for all phases", () => {
    const pd = stream.phaseDone.value;
    for (const phase of PHASE_ORDER) {
      expect(pd[phase]).toEqual({ done: 0, total: 0 });
    }
  });

  it("phaseDone has entries for exactly the phases in PHASE_ORDER", () => {
    const pd = stream.phaseDone.value;
    const keys = Object.keys(pd);
    expect(keys.sort()).toEqual([...PHASE_ORDER].sort());
  });
});

describe("abort", () => {
  let stream: UseProcessingStream;

  beforeEach(() => {
    stream = useProcessingStream();
  });

  it("resets state to idle", () => {
    stream.state.value = "running";
    stream.abort();
    expect(stream.state.value).toBe("idle");
  });

  it("resets tripIndex to 0", () => {
    stream.tripIndex.value = 5;
    stream.abort();
    expect(stream.tripIndex.value).toBe(0);
  });

  it("clears errorDetail", () => {
    stream.errorDetail.value = "some error";
    stream.abort();
    expect(stream.errorDetail.value).toBeNull();
  });

  it("resets phaseDone to fresh zeroed values", () => {
    stream.phaseDone.value.elevations = { done: 10, total: 20 };
    stream.phaseDone.value.weather = { done: 5, total: 10 };
    stream.abort();

    for (const phase of PHASE_ORDER) {
      expect(stream.phaseDone.value[phase]).toEqual({ done: 0, total: 0 });
    }
  });

  it("is safe to call multiple times", () => {
    stream.abort();
    stream.abort();
    stream.abort();
    expect(stream.state.value).toBe("idle");
  });

  it("is safe to call from idle state", () => {
    expect(stream.state.value).toBe("idle");
    stream.abort();
    expect(stream.state.value).toBe("idle");
  });
});
