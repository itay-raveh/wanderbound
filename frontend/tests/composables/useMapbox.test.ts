import { mount } from "@vue/test-utils";
import mapboxgl from "mapbox-gl";
import { defineComponent, nextTick, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useMapbox } from "@/composables/useMapbox";

function latestMap() {
  const mocked = vi.mocked(mapboxgl.Map);
  return mocked.mock.results[mocked.mock.results.length - 1].value as {
    areTilesLoaded: ReturnType<typeof vi.fn>;
    getCanvas: ReturnType<typeof vi.fn>;
    once: ReturnType<typeof vi.fn>;
  };
}

function fireIdle(map: ReturnType<typeof latestMap>) {
  const idleCall = map.once.mock.calls.findLast(([event]) => event === "idle");
  expect(idleCall).toBeTruthy();
  idleCall?.[1]();
}

describe("useMapbox", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("snapshots the WebGL canvas for print capture when the map is ready", async () => {
    const TestComponent = defineComponent({
      setup() {
        const container = ref<HTMLElement | null>(null);
        useMapbox({ container, preserveDrawingBuffer: true });
        return { container };
      },
      template: '<div><div ref="container" data-testid="map" /></div>',
    });

    const wrapper = mount(TestComponent);
    await nextTick();
    const el = wrapper.get('[data-testid="map"]').element as HTMLElement;
    expect(el.dataset.map).toBe("");
    const map = latestMap();
    map.areTilesLoaded.mockReturnValue(true);
    map.getCanvas.mockReturnValue({
      width: 800,
      height: 600,
      toDataURL: vi.fn(() => "data:image/png;base64,map"),
    });
    expect(map.areTilesLoaded()).toBe(true);

    fireIdle(map);

    const snapshot = el.querySelector<HTMLImageElement>(
      ".mapbox-print-snapshot",
    );
    expect(el.dataset.mapReady).toBe("");
    expect(el.dataset.mapSnapshotReady).toBe("");
    expect(snapshot?.src).toBe("data:image/png;base64,map");
    expect(snapshot?.getAttribute("aria-hidden")).toBe("true");
  });
});
