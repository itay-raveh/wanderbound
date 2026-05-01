import { flushPromises } from "@vue/test-utils";
import { withSetup } from "../helpers";
import {
  PHASE_ORDER,
  useTripProcessingStream,
} from "@/composables/useTripProcessingStream";
import { processUser } from "@/client";

vi.mock("@/client", () => ({
  processUser: vi.fn(),
}));

const mockedProcessUser = vi.mocked(processUser);

async function* streamEvents(events: unknown[]) {
  for (const event of events) {
    await Promise.resolve();
    yield event;
  }
}

async function waitForStream() {
  await flushPromises();
  await new Promise((resolve) => setTimeout(resolve));
  await flushPromises();
}

describe("useTripProcessingStream", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  test("phase order includes segment discovery", () => {
    expect(PHASE_ORDER).toEqual([
      "elevations",
      "weather",
      "segments",
      "layouts",
    ]);
  });

  test("aggregates segment counts across trips", async () => {
    mockedProcessUser.mockResolvedValue({
      stream: streamEvents([
        { type: "trip_start", trip_index: 0 },
        { type: "segments_found", hikes: 1, walks: 2, drives: 3, flights: 4 },
        { type: "trip_start", trip_index: 1 },
        { type: "segments_found", hikes: 2, walks: 0, drives: 1, flights: 0 },
      ]),
    } as Awaited<ReturnType<typeof processUser>>);
    const stream = withSetup(useTripProcessingStream);

    stream.start();
    await waitForStream();

    expect(stream.segmentSummary.value).toEqual({
      hikes: 3,
      walks: 2,
      drives: 4,
      flights: 4,
    });
  });
});
