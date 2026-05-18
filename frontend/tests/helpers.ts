import {
  computed,
  createApp,
  defineComponent,
  h,
  ref,
  type Component,
} from "vue";
import { mount, type ComponentMountingOptions } from "@vue/test-utils";
import type { Mock } from "vitest";
import { createPinia } from "pinia";
import { PiniaColada } from "@pinia/colada";
import { Quasar } from "quasar";
import i18n from "@/i18n";
import { client } from "@/client/client.gen";
import type {
  AlbumMedia,
  Location,
  Segment,
  StepRead as Step,
  Weather,
  WeatherData,
} from "@/client";
import { provideAlbum } from "@/composables/useAlbum";
import {
  DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
  type MediaResolutionWarningPreset,
} from "@/utils/photoQuality";

// Set base URL for test API calls (MSW intercepts these).
client.setConfig({ baseUrl: "http://localhost:8000" });

/**
 * Mount a composable in a minimal app with Pinia + PiniaColada + Quasar.
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

export function withParentSetup<T>(
  parentSetup: () => void,
  composable: () => T,
  { plugins = true }: { plugins?: boolean } = {},
): { result: T; unmount: () => void } {
  let result!: T;
  const Child = defineComponent({
    setup() {
      result = composable();
      return () => null;
    },
  });
  const Parent = defineComponent({
    setup() {
      parentSetup();
      return () => h(Child);
    },
  });
  const app = createApp(Parent);
  if (plugins) {
    app.use(createPinia());
    app.use(PiniaColada);
    app.use(Quasar, {});
    app.use(i18n);
  }
  app.mount(document.createElement("div"));
  const unmount = () => app.unmount();
  onTestFinished(unmount);
  return { result, unmount };
}

export function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

export function makeAlbumMedia(
  overrides: Partial<AlbumMedia> = {},
): AlbumMedia {
  return {
    uid: 1,
    aid: "album-1",
    name: "photo.jpg",
    kind: "photo",
    width: 1920,
    height: 1080,
    byte_size: 1234,
    upgrade_candidate: false,
    created_at: "2026-05-13T12:00:00Z",
    updated_at: "2026-05-13T12:34:56Z",
    ...overrides,
  };
}

export function makeLocation(overrides: Partial<Location> = {}): Location {
  return {
    lat: 0,
    lon: 0,
    name: "Place",
    detail: "",
    country_code: "US",
    ...overrides,
  };
}

export function makeWeather({
  day = {},
  night = null,
}: {
  day?: Partial<WeatherData>;
  night?: Partial<WeatherData> | null;
} = {}): Weather {
  return {
    day: { temp: 20, feels_like: 18, icon: "clear-day", ...day },
    night: night && { temp: 10, feels_like: 8, icon: "clear-night", ...night },
  };
}

export function mockReadyGooglePickerSession(googlePhotosMock: {
  closeSession: Mock;
  createPickerSession: Mock;
  pollSession: Mock;
}) {
  googlePhotosMock.createPickerSession.mockResolvedValue({
    sessionId: "session-1",
    pickerUri: "https://photos.google.com/picker/session-1",
  });
  googlePhotosMock.pollSession.mockResolvedValue({ ready: true });
  googlePhotosMock.closeSession.mockResolvedValue(undefined);
}

export function resetGooglePhotosMock(googlePhotosMock: {
  authorize: Mock;
  closeSession: Mock;
  createPickerSession: Mock;
  isConnected: { value: boolean };
  pollSession: Mock;
  state: { value: string };
}) {
  googlePhotosMock.authorize.mockReset();
  googlePhotosMock.closeSession.mockReset();
  googlePhotosMock.createPickerSession.mockReset();
  googlePhotosMock.pollSession.mockReset();
  googlePhotosMock.isConnected.value = true;
  googlePhotosMock.state.value = "connected";
}

export function mockGooglePickerPopup() {
  const popup = {
    close: vi.fn(),
    document: {
      body: { style: {}, textContent: "" },
      title: "",
    },
    location: { href: "" },
  };
  vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
  return popup;
}

export function provideTestAlbum({
  albumId = "album-1",
  colors = {},
  media = [],
  tripStart = "2024-01-01",
  totalDays = 1,
  mediaResolutionWarningPreset = DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
}: {
  albumId?: string;
  colors?: Record<string, string>;
  media?: AlbumMedia[];
  tripStart?: string;
  totalDays?: number;
  mediaResolutionWarningPreset?: MediaResolutionWarningPreset;
} = {}) {
  return provideAlbum({
    albumId: ref(albumId),
    colors: computed(() => colors),
    media: computed(() => media),
    tripStart: computed(() => tripStart),
    totalDays: computed(() => totalDays),
    mediaResolutionWarningPreset: computed(() => mediaResolutionWarningPreset),
  });
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
    location: makeLocation(),
    elevation: 0,
    weather: makeWeather(),
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
