import { createApp, type Component } from "vue";
import { mount, type ComponentMountingOptions } from "@vue/test-utils";
import { createPinia } from "pinia";
import { PiniaColada } from "@pinia/colada";
import { Quasar } from "quasar";
import i18n from "@/i18n";
import { client } from "@/client/client.gen";
import type { Step, Segment, SegmentOutline } from "@/client";

// Set base URL for test API calls (MSW intercepts these).
client.setConfig({ baseUrl: "http://localhost:8000" });

/**
 * Mount a composable in a minimal app with Pinia + PiniaColada + Quasar.
 * Call `cleanup()` when done, or use `onTestFinished` for auto-cleanup.
 */
export function withSetup<T>(composable: () => T): T {
  let result!: T;
  const app = createApp({
    setup() {
      result = composable();
      return () => null;
    },
  });
  app.use(createPinia());
  app.use(PiniaColada);
  app.use(Quasar, {});
  app.use(i18n);
  app.mount(document.createElement("div"));

  onTestFinished(() => {
    app.unmount();
  });

  return result;
}

/** Shared plugin list for mounting components under test. */
const testPlugins = [[Quasar, {}], createPinia(), PiniaColada, i18n] as const;

/** Mount a component with the standard test plugin stack. */
export function mountWithPlugins<T extends Component>(
  component: T,
  options: ComponentMountingOptions<T> = {},
) {
  const { global: g, ...rest } = options;
  return mount(component, {
    global: { plugins: [...testPlugins] as never, ...g },
    ...rest,
  } as ComponentMountingOptions<T>);
}

export function makeStep(overrides: Partial<Step> = {}): Step {
  return {
    id: 1,
    name: "Test Step",
    description: "",
    cover: null,
    pages: [],
    unused: [],
    uid: 1,
    aid: "a1",
    timestamp: 1704067200,
    timezone_id: "UTC",
    location: { lat: 0, lon: 0, name: "Place", detail: "", country_code: "US" },
    elevation: 0,
    weather: {
      day: { temp: 20, feels_like: 18, icon: "clear-day" },
      night: null,
    },
    datetime: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

export function makeSegment(overrides: Partial<Segment> = {}): Segment {
  return {
    uid: 1,
    aid: "a1",
    start_time: 0,
    end_time: 100,
    kind: "driving",
    timezone_id: "UTC",
    points: [],
    route: null,
    ...overrides,
  };
}

export function makeSegmentOutline(overrides: Partial<SegmentOutline> = {}): SegmentOutline {
  return {
    start_time: 0,
    end_time: 100,
    kind: "driving",
    timezone_id: "UTC",
    start_coord: [0, 0],
    end_coord: [1, 1],
    ...overrides,
  };
}
