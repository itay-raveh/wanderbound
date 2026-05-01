import { mountWithPlugins } from "../helpers";
import TripTimeline from "@/components/register/TripTimeline.vue";
import type {
  PhaseDone,
  ProcessingPhase,
} from "@/composables/useTripProcessingStream";
import type { TripMeta } from "@/client";

const trip: TripMeta = {
  id: "trip-1",
  title: "Test Trip",
  step_count: 3,
  country_codes: ["US"],
};

function phaseDone(
  overrides: Partial<Record<ProcessingPhase, { done: number; total: number }>>,
): PhaseDone {
  return {
    elevations: { done: 0, total: 0 },
    weather: { done: 0, total: 0 },
    segments: { done: 0, total: 0 },
    layouts: { done: 0, total: 0 },
    ...overrides,
  };
}

function mountTimeline(done: PhaseDone) {
  return mountWithPlugins(TripTimeline, {
    props: {
      trips: [trip],
      state: "running",
      tripIndex: 0,
      phaseDone: done,
    },
  });
}

describe("TripTimeline phase progress", () => {
  test("renders active zero-progress phases as indeterminate without a counter", () => {
    const wrapper = mountTimeline(phaseDone({ segments: { done: 0, total: 1 } }));
    const bar = wrapper.getComponent({ name: "QLinearProgress" });

    expect(bar.props("indeterminate")).toBe(true);
    expect(wrapper.text()).not.toContain("0/1");
  });

  test("renders determinate progress and counter after progress starts", () => {
    const wrapper = mountTimeline(phaseDone({ segments: { done: 1, total: 2 } }));
    const bar = wrapper.getComponent({ name: "QLinearProgress" });

    expect(bar.props("indeterminate")).toBe(false);
    expect(bar.props("value")).toBe(0.5);
    expect(wrapper.text()).toContain("1/2");
  });
});
