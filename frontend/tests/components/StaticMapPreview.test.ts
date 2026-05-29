import { mount } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import StaticMapPreview from "@/components/album/map/StaticMapPreview.vue";

describe("StaticMapPreview", () => {
  test("renders route and step markers without Mapbox", () => {
    const wrapper = mount(StaticMapPreview, {
      props: {
        steps: [
          {
            id: 1,
            name: "Start",
            location: { lat: 10, lon: 20 },
          },
          {
            id: 2,
            name: "End",
            location: { lat: 15, lon: 25 },
          },
        ],
        segmentOutlines: [
          {
            start_time: 1,
            end_time: 2,
            kind: "driving",
            timezone_id: "UTC",
            start_coord: [10, 20],
            end_coord: [15, 25],
          },
        ],
      },
    });

    expect(wrapper.find(".page-container").exists()).toBe(true);
    expect(wrapper.find("svg").exists()).toBe(true);
    expect(wrapper.findAll(".static-map-route")).toHaveLength(1);
    expect(wrapper.findAll(".static-map-marker")).toHaveLength(2);
  });
});
