import { computed, defineComponent, h, ref } from "vue";
import { flushPromises } from "@vue/test-utils";
import CoverPage from "@/components/album/CoverPage.vue";
import MediaItem from "@/components/album/MediaItem.vue";
import PanoramaSpreadPage from "@/components/album/PanoramaSpreadPage.vue";
import StepPhotoPage from "@/components/album/step/StepPhotoPage.vue";
import StepEntry from "@/components/album/StepEntry.vue";
import { provideAlbum } from "@/composables/useAlbum";
import { provideStepMutate } from "@/composables/useStepLayout";
import { DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET } from "@/utils/photoQuality";
import { Notify } from "quasar";
import { makeAlbumMedia, makeStep, mountWithPlugins, provideTestAlbum } from "../helpers";
import { mockAlbum } from "../fixtures/mocks";

vi.mock("@/components/editor/PanoramaFrameDialog.vue", () => ({
  default: {
    props: ["modelValue", "albumId", "media", "destination"],
    emits: ["update:modelValue", "applied"],
    template: `
      <div
        v-if="modelValue"
        class="panorama-dialog-stub"
        :data-kind="destination.kind"
        :data-aspect="destination.aspect_ratio"
        :data-width="destination.width_px"
        :data-height="destination.height_px"
      />
    `,
  },
}));

vi.mock("@/queries/useAlbumMutation", () => ({
  useAlbumMutation: () => ({ mutate: vi.fn() }),
}));

vi.mock("@/queries/useUserQuery", () => ({
  useUserQuery: () => ({
    formatDateRange: () => "January 1, 2024",
    countryName: () => "Country",
  }),
}));

vi.mock("vue-draggable-plus", () => ({
  useDraggable: () => ({
    start: vi.fn(),
    destroy: vi.fn(),
  }),
}));

const activePanorama = makeAlbumMedia({
  name: "wide.jpg",
  width: 4000,
  height: 1000,
  panorama: {
    status: "active",
    detection: "gpano",
    source_width: 4000,
    source_height: 1000,
    captured_fov: 180,
    revision: 4,
  },
});
const notify = vi.fn();

function rect(width: number, height: number): DOMRect {
  return {
    x: 0,
    y: 0,
    top: 0,
    right: width,
    bottom: height,
    left: 0,
    width,
    height,
    toJSON: () => ({}),
  };
}

function mountMedia(media = activePanorama) {
  const Parent = defineComponent({
    setup() {
      provideTestAlbum({ media: [media] });
      return () =>
        h(MediaItem, {
          media: media.name,
          lazy: false,
          panoramaDestinationKind: "grid",
        });
    },
  });
  return mountWithPlugins(Parent);
}

describe("panorama placement controls", () => {
  beforeEach(() => {
    notify.mockReset();
    Object.defineProperty(Notify, "create", {
      configurable: true,
      value: notify,
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
      function () {
        if (this.classList.contains("panorama-page")) return rect(900, 600);
        if (this.closest(".cover-page")) return rect(1200, 800);
        return rect(600, 300);
      },
    );
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  test("active and suggested panoramas expose the appropriate immediate action", () => {
    expect(mountMedia().get(".panorama-frame-action").text()).toBe(
      "Frame panorama",
    );

    const suggested = {
      ...activePanorama,
      panorama: { ...activePanorama.panorama!, status: "suggested" as const },
    };
    expect(mountMedia(suggested).get(".panorama-frame-action").text()).toBe(
      "Treat as panorama",
    );
  });

  test("a grid opens the lazy framing dialog with its measured destination", async () => {
    const wrapper = mountMedia();

    await wrapper.get(".panorama-frame-action").trigger("click");
    await flushPromises();

    expect(wrapper.get(".panorama-dialog-stub").attributes()).toMatchObject({
      "data-kind": "grid",
      "data-aspect": "2",
      "data-width": "600",
      "data-height": "300",
    });
  });

  test("a one-photo page uses the full-page destination and offers a spread", async () => {
    const Parent = defineComponent({
      setup() {
        provideTestAlbum({ media: [activePanorama] });
        return () =>
          h(StepPhotoPage, {
            page: { kind: "grid", media: [activePanorama.name] },
          });
      },
    });
    const wrapper = mountWithPlugins(Parent, {
      global: { stubs: { StepMainPage: true, StepDescriptionPage: true } },
    });

    await wrapper.get(".panorama-frame-action").trigger("click");
    await flushPromises();

    expect(wrapper.get(".panorama-dialog-stub").attributes("data-kind")).toBe(
      "full_page",
    );
    expect(wrapper.get(".panorama-spread-action").text()).toBe(
      "Make two-page spread",
    );
  });

  test("a spread opens one framing dialog for the full two-page aspect", async () => {
    const Parent = defineComponent({
      setup() {
        provideTestAlbum({ media: [activePanorama] });
        return () =>
          h(PanoramaSpreadPage, { media: activePanorama.name, side: "left" });
      },
    });
    const wrapper = mountWithPlugins(Parent, {
      global: { stubs: { StepMainPage: true, StepDescriptionPage: true } },
    });

    await wrapper.get(".panorama-frame-action").trigger("click");
    await flushPromises();

    expect(wrapper.get(".panorama-dialog-stub").attributes()).toMatchObject({
      "data-kind": "panorama_spread",
      "data-aspect": "3",
      "data-width": "1800",
      "data-height": "600",
    });
  });

  test("a spread excludes its editor border from the full destination", async () => {
    let resizeCallback: ResizeObserverCallback | undefined;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: ResizeObserverCallback) {
          resizeCallback = callback;
        }
        observe() {}
        disconnect() {}
      },
    );
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
      function () {
        if (this.classList.contains("panorama-page")) return rect(897, 636);
        return rect(600, 300);
      },
    );
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(
      function () {
        return this.classList.contains("panorama-page") ? 891 : 0;
      },
    );
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(
      function () {
        return this.classList.contains("panorama-page") ? 630 : 0;
      },
    );
    const Parent = defineComponent({
      setup() {
        provideTestAlbum({ media: [activePanorama] });
        return () =>
          h(PanoramaSpreadPage, { media: activePanorama.name, side: "left" });
      },
    });
    const wrapper = mountWithPlugins(Parent);
    await wrapper.vm.$nextTick();

    const initialSrc = new URL(wrapper.get("img").attributes("src"));
    expect(initialSrc.searchParams.get("w")).toBe("1782");
    expect(initialSrc.searchParams.get("h")).toBe("630");

    const page = wrapper.get(".panorama-page").element;
    resizeCallback?.(
      [
        {
          target: page,
          contentBoxSize: [{ inlineSize: 594, blockSize: 420 }],
          contentRect: rect(594, 420),
        } as unknown as ResizeObserverEntry,
      ],
      {} as ResizeObserver,
    );
    await wrapper.vm.$nextTick();

    const resizedSrc = new URL(wrapper.get("img").attributes("src"));
    expect(resizedSrc.searchParams.get("w")).toBe("1188");
    expect(resizedSrc.searchParams.get("h")).toBe("420");

    await wrapper.get(".panorama-frame-action").trigger("click");
    await flushPromises();

    expect(wrapper.get(".panorama-dialog-stub").attributes()).toMatchObject({
      "data-kind": "panorama_spread",
      "data-aspect": String((297 * 2) / 210),
      "data-width": "1188",
      "data-height": "420",
    });
  });

  test("a spread can return to a one-photo full page", async () => {
    const mutate = vi.fn();
    const step = makeStep({
      id: 7,
      pages: [{ kind: "panorama_spread", media: [activePanorama.name] }],
    });
    const Parent = defineComponent({
      setup() {
        provideTestAlbum({ media: [activePanorama] });
        provideStepMutate(mutate);
        return () => h(StepEntry, { step });
      },
    });
    const wrapper = mountWithPlugins(Parent, {
      global: { stubs: { StepMainPage: true, StepDescriptionPage: true } },
    });

    await wrapper.get(".panorama-full-page-action").trigger("click");

    expect(mutate).toHaveBeenCalledWith({
      sid: 7,
      update: {
        pages: [{ kind: "grid", media: [activePanorama.name] }],
      },
    });
  });

  test("a chapter cover opens the framing dialog with the cover aspect", async () => {
    const chapter = {
      id: "chapter-2",
      title: "Trip",
      subtitle: "",
      step_ids: [1],
      front_cover_photo: activePanorama.name,
      back_cover_photo: null,
      front_cover_darkness: 0.2,
    };
    const album = { ...mockAlbum, chapters: [chapter] };
    const Parent = defineComponent({
      setup() {
        provideTestAlbum({ media: [activePanorama] });
        return () =>
          h(CoverPage, {
            album,
            chapter,
            steps: [makeStep({ id: 1, datetime: "2024-01-01T00:00:00Z" })],
          });
      },
    });
    const wrapper = mountWithPlugins(Parent, {
      global: { stubs: { StepMainPage: true, StepDescriptionPage: true } },
    });

    await wrapper.get(".panorama-frame-action").trigger("click");
    await flushPromises();

    expect(wrapper.get(".panorama-dialog-stub").attributes()).toMatchObject({
      "data-kind": "cover",
      "data-aspect": "1.5",
      "data-width": "1200",
      "data-height": "800",
    });
  });

  test("every rendered use follows the authoritative saved revision", async () => {
    const media = ref([activePanorama]);
    const Parent = defineComponent({
      setup() {
        provideAlbum({
          albumId: ref("album-1"),
          colors: computed(() => ({})),
          media: computed(() => media.value),
          tripStart: computed(() => "2024-01-01"),
          totalDays: computed(() => 1),
          mediaResolutionWarningPreset: computed(
            () => DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
          ),
        });
        return () =>
          h("div", [
            h(MediaItem, {
              media: activePanorama.name,
              lazy: false,
              panoramaDestinationKind: "grid",
            }),
            h(MediaItem, {
              media: activePanorama.name,
              lazy: false,
              panoramaDestinationKind: "grid",
            }),
          ]);
      },
    });
    const wrapper = mountWithPlugins(Parent, {
      global: { stubs: { StepMainPage: true, StepDescriptionPage: true } },
    });

    media.value = [
      {
        ...activePanorama,
        panorama: { ...activePanorama.panorama!, revision: 5 },
      },
    ];
    await wrapper.vm.$nextTick();

    const revisions = wrapper.findAll("img").map((image) =>
      new URL(image.attributes("src")).searchParams.get("panorama_revision"),
    );
    expect(revisions).toEqual(["5", "5"]);
  });

  test("converts a one-photo grid to a spread in one complete layout mutation", async () => {
    const mutate = vi.fn();
    const step = makeStep({
      id: 7,
      pages: [
        { kind: "grid", media: ["before.jpg"] },
        { kind: "grid", media: [activePanorama.name] },
        { kind: "grid", media: ["after.jpg"] },
      ],
    });
    const Parent = defineComponent({
      setup() {
        provideTestAlbum({ media: [activePanorama] });
        provideStepMutate(mutate);
        return () => h(StepEntry, { step });
      },
    });
    const wrapper = mountWithPlugins(Parent, {
      global: { stubs: { StepMainPage: true, StepDescriptionPage: true } },
    });

    await wrapper.get(".panorama-spread-action").trigger("click");

    expect(mutate).toHaveBeenCalledOnce();
    expect(mutate).toHaveBeenCalledWith({
      sid: 7,
      update: {
        pages: [
          { kind: "grid", media: ["before.jpg"] },
          { kind: "panorama_spread", media: [activePanorama.name] },
          { kind: "grid", media: ["after.jpg"] },
        ],
      },
    });
  });

  test("moves a panorama from a multi-photo grid to its own full page atomically", async () => {
    const mutate = vi.fn();
    const step = makeStep({
      id: 7,
      pages: [
        { kind: "grid", media: [activePanorama.name, "other.jpg"] },
        { kind: "grid", media: ["after.jpg"] },
      ],
    });
    const Parent = defineComponent({
      setup() {
        provideTestAlbum({
          media: [activePanorama, makeAlbumMedia({ name: "other.jpg" })],
        });
        provideStepMutate(mutate);
        return () => h(StepEntry, { step });
      },
    });
    const wrapper = mountWithPlugins(Parent, {
      global: { stubs: { StepMainPage: true, StepDescriptionPage: true } },
    });

    await wrapper.get(".panorama-full-page-action").trigger("click");

    expect(mutate).toHaveBeenCalledWith({
      sid: 7,
      update: {
        pages: [
          { kind: "grid", media: ["other.jpg"] },
          { kind: "grid", media: [activePanorama.name] },
          { kind: "grid", media: ["after.jpg"] },
        ],
      },
    });
  });

  test("shows a dismissible lay-flat recommendation without blocking conversion when storage fails", async () => {
    const mutate = vi.fn();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Storage disabled", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Storage disabled", "SecurityError");
    });
    const step = makeStep({
      id: 7,
      pages: [{ kind: "grid", media: [activePanorama.name] }],
    });
    const Parent = defineComponent({
      setup() {
        provideTestAlbum({ media: [activePanorama] });
        provideStepMutate(mutate);
        return () => h(StepEntry, { step });
      },
    });
    const wrapper = mountWithPlugins(Parent, {
      global: { stubs: { StepMainPage: true, StepDescriptionPage: true } },
    });

    await wrapper.get(".panorama-spread-action").trigger("click");

    expect(notify).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "info",
        message:
          "For the best result, print panorama spreads in a lay-flat photo book.",
        actions: [expect.objectContaining({ label: "Got it" })],
      }),
    );
    expect(mutate).toHaveBeenCalledOnce();
  });

  test("does not repeat the general lay-flat recommendation after dismissal", async () => {
    const mutate = vi.fn();
    const step = makeStep({
      id: 7,
      pages: [{ kind: "grid", media: [activePanorama.name] }],
    });
    const Parent = defineComponent({
      setup() {
        provideTestAlbum({ media: [activePanorama] });
        provideStepMutate(mutate);
        return () => h(StepEntry, { step });
      },
    });
    const wrapper = mountWithPlugins(Parent, {
      global: { stubs: { StepMainPage: true, StepDescriptionPage: true } },
    });
    const action = wrapper.get(".panorama-spread-action");

    await action.trigger("click");
    const notification = notify.mock.calls[0]?.[0] as {
      actions: Array<{ handler: () => void }>;
    };
    notification.actions[0].handler();
    await action.trigger("click");

    expect(notify).toHaveBeenCalledOnce();
    expect(localStorage.getItem("lay-flat-recommendation-dismissed")).toBe(
      "true",
    );
  });
});
