import { defineComponent, h, nextTick, ref, readonly } from "vue";
import { makeAlbumMedia, mountWithPlugins, provideTestAlbum } from "../helpers";
import MediaItem from "@/components/album/MediaItem.vue";
import { STEP_ID_KEY, usePhotoFocus } from "@/composables/usePhotoFocus";
import { PROGRAMMATIC_SCROLL_KEY } from "@/composables/useProgrammaticScroll";
import { providePrintMode } from "@/composables/usePrintReady";

const mutateAsync = vi.fn();
let playSpy: ReturnType<typeof vi.spyOn>;
const MEDIA_UPDATED_AT = "2026-05-13T12:34:56Z";

function expectCacheBustedMediaSource(src: string | undefined) {
  expect(src).toBeDefined();
  const url = new URL(src!);
  expect(url.pathname).toBe("/api/v1/albums/album-1/media/photo.jpg");
  expect(url.searchParams.get("d")).toBe(MEDIA_UPDATED_AT);
}

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];

  readonly callback: IntersectionObserverCallback;
  readonly observe = vi.fn();
  readonly disconnect = vi.fn();

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
    MockIntersectionObserver.instances.push(this);
  }

  trigger(isIntersecting: boolean) {
    this.callback(
      [
        {
          isIntersecting,
          time: performance.now(),
        } as IntersectionObserverEntry,
      ],
      this as unknown as IntersectionObserver,
    );
  }
}

vi.mock("@/queries/useVideoFrameMutation", () => ({
  useVideoFrameMutation: () => ({ mutateAsync }),
}));

function mountMediaItem(
  media: ReturnType<typeof makeAlbumMedia>,
  props: Record<string, unknown>,
  provide: Record<symbol, unknown>,
  printMode = false,
) {
  const Wrapper = defineComponent({
    setup() {
      provideTestAlbum({ media: [media] });
      if (printMode) providePrintMode();
      return () => h(MediaItem, props);
    },
  });

  return mountWithPlugins(Wrapper, {
    global: {
      provide,
    },
    attachTo: document.body,
  });
}

function mountVideoItem() {
  return mountMediaItem(
    makeAlbumMedia({ name: "clip.mp4", kind: "video" }),
    { media: "clip.mp4", alt: "Clip" },
    { [STEP_ID_KEY as symbol]: 7 },
  );
}

function mountPhotoItem(
  programmaticScrolling = ref(false),
  props: Record<string, unknown> = {},
  mediaOverrides: Partial<ReturnType<typeof makeAlbumMedia>> = {},
) {
  return mountMediaItem(
    makeAlbumMedia({ updated_at: MEDIA_UPDATED_AT, ...mediaOverrides }),
    { media: "photo.jpg", alt: "Photo", ...props },
    {
      [STEP_ID_KEY as symbol]: 7,
      [PROGRAMMATIC_SCROLL_KEY as symbol]: readonly(programmaticScrolling),
    },
  );
}

describe("MediaItem video controls", () => {
  beforeEach(() => {
    mutateAsync.mockResolvedValue(undefined);
    playSpy = vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  });

  afterEach(() => {
    usePhotoFocus().blur();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  test("renders inline mobile video playback", () => {
    const wrapper = mountVideoItem();

    expect(wrapper.get("video").attributes("playsinline")).toBeDefined();
  });

  test("clicking play overlay starts playback without selecting the media item", async () => {
    const focus = vi.spyOn(usePhotoFocus(), "focus");
    const wrapper = mountVideoItem();

    await wrapper.get(".play-overlay").trigger("click");

    expect(playSpy).toHaveBeenCalled();
    expect(focus).not.toHaveBeenCalled();
  });

  test("Enter opens the inline player and focuses the video", async () => {
    const wrapper = mountVideoItem();
    const video = wrapper.get("video").element as HTMLVideoElement;

    await wrapper.get(".media-item").trigger("keydown", { key: "Enter" });
    await nextTick();

    expect(playSpy).toHaveBeenCalled();
    expect(document.activeElement).toBe(video);
  });

  test("moves focus back to the media item when playback ends", async () => {
    const wrapper = mountVideoItem();
    const root = wrapper.get(".media-item").element as HTMLElement;
    const video = wrapper.get("video").element as HTMLVideoElement;

    await wrapper.get(".play-overlay").trigger("click");
    video.focus();
    expect(document.activeElement).toBe(video);

    await wrapper.get("video").trigger("ended");

    expect(document.activeElement).toBe(root);
  });

  test("moves focus back to the media item after choosing a poster frame", async () => {
    const wrapper = mountVideoItem();
    const root = wrapper.get(".media-item").element as HTMLElement;
    const video = wrapper.get("video").element as HTMLVideoElement;

    await wrapper.get(".play-overlay").trigger("click");
    video.focus();
    expect(document.activeElement).toBe(video);

    await wrapper.get(".set-frame-btn").trigger("click");

    expect(mutateAsync).toHaveBeenCalledWith({
      name: "clip.mp4",
      timestamp: 0,
    });
    expect(document.activeElement).toBe(root);
  });

  test("keeps an already assigned image src during programmatic scroll", async () => {
    MockIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
    const programmaticScrolling = ref(false);
    const wrapper = mountPhotoItem(programmaticScrolling);
    await nextTick();
    MockIntersectionObserver.instances.at(-1)?.trigger(true);
    await nextTick();
    const img = wrapper.get("img");

    const initialSrc = img.attributes("src");
    expectCacheBustedMediaSource(initialSrc);

    programmaticScrolling.value = true;
    await nextTick();

    expect(img.attributes("src")).toBe(initialSrc);
  });

  test("marks only selectable media as draggable", () => {
    const selectable = mountPhotoItem();
    const staticItem = mountPhotoItem(ref(false), { focusable: false });

    expect(selectable.get(".media-item").classes()).toContain("selectable");
    expect(staticItem.get(".media-item").classes()).not.toContain("selectable");
  });

  test("uses updated_at to bust immutable media URLs after same-size replacements", () => {
    const wrapper = mountPhotoItem(
      ref(false),
      { lazy: false },
      { updated_at: "2026-05-13T12:34:56Z" },
    );

    expectCacheBustedMediaSource(wrapper.get("img").attributes("src"));
  });

  test("allows a disabled panorama to be enabled again", () => {
    const wrapper = mountPhotoItem(
      ref(false),
      { panoramaDestinationKind: "grid" },
      {
        panorama: {
          status: "disabled",
          detection: "dimensions",
          source_width: 1600,
          source_height: 800,
          captured_fov: 180,
          revision: 2,
        },
      },
    );

    expect(wrapper.get(".panorama-frame-action").text()).toBe(
      "Treat as panorama",
    );
  });

  test("renders resolution warnings as an icon badge without a tint overlay", () => {
    const wrapper = mountPhotoItem(ref(false), {
      quality: { tier: "warning", dpi: 72 },
    });

    expect(wrapper.find(".quality-overlay").exists()).toBe(false);
    expect(wrapper.find(".quality-badge.warning").exists()).toBe(true);
  });

  test("requests an active panorama rendition at the placement device-pixel dimensions", async () => {
    vi.stubGlobal("devicePixelRatio", 2);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      width: 640,
      height: 320,
    } as DOMRect);
    const wrapper = mountPhotoItem(
      ref(false),
      { lazy: false, panoramaDestinationKind: "grid" },
      {
        panorama: {
          status: "active",
          detection: "gpano",
          source_width: 4000,
          source_height: 1000,
          captured_fov: 180,
          revision: 9,
        },
      },
    );
    await nextTick();

    const src = new URL(wrapper.get("img").attributes("src"));
    expect(src.searchParams.get("w")).toBe("1280");
    expect(src.searchParams.get("h")).toBe("640");
    expect(src.searchParams.get("panorama_revision")).toBe("9");
  });

  test("keeps a high-DPI panorama rendition within the backend output limit", async () => {
    vi.stubGlobal("devicePixelRatio", 2);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      width: 5000,
      height: 2500,
    } as DOMRect);
    const wrapper = mountPhotoItem(
      ref(false),
      { lazy: false, panoramaDestinationKind: "grid" },
      {
        panorama: {
          status: "active",
          detection: "gpano",
          source_width: 10_000,
          source_height: 5000,
          captured_fov: 180,
          revision: 9,
        },
      },
    );
    await nextTick();

    const src = new URL(wrapper.get("img").attributes("src"));
    expect(src.searchParams.get("w")).toBe("8192");
    expect(src.searchParams.get("h")).toBe("4096");
  });

  test("requests a 300-PPI active panorama rendition in print mode", async () => {
    vi.stubGlobal("devicePixelRatio", 2);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      width: (297 * 96) / 25.4,
      height: (210 * 96) / 25.4,
    } as DOMRect);
    const media = makeAlbumMedia({
      panorama: {
        status: "active",
        detection: "gpano",
        source_width: 8000,
        source_height: 4000,
        captured_fov: 180,
        revision: 9,
      },
    });
    const wrapper = mountMediaItem(
      media,
      {
        media: "photo.jpg",
        lazy: false,
        panoramaDestinationKind: "full_page",
      },
      {},
      true,
    );
    await nextTick();

    const src = new URL(wrapper.get("img").attributes("src"));
    expect(src.searchParams.get("w")).toBe("3508");
    expect(src.searchParams.get("h")).toBe("2480");
    expect(src.searchParams.get("panorama_revision")).toBe("9");
  });

  test("keeps ordinary media on its existing URL path on high-DPI displays", async () => {
    vi.stubGlobal("devicePixelRatio", 2);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      width: 640,
      height: 320,
    } as DOMRect);
    const wrapper = mountPhotoItem(ref(false), { lazy: false });
    await nextTick();

    const src = new URL(wrapper.get("img").attributes("src"));
    expect(src.pathname).toBe("/api/v1/albums/album-1/media/photo.jpg");
    expect(src.searchParams.get("d")).toBe(MEDIA_UPDATED_AT);
    expect(src.searchParams.get("w")).toBe("800");
    expect(src.searchParams.has("h")).toBe(false);
    expect(src.searchParams.has("panorama_revision")).toBe(false);
  });

  test("registers multiple resolution badges without recursive updates", async () => {
    const first = mountPhotoItem(ref(false), {
      quality: { tier: "warning", dpi: 72 },
    });
    const second = mountPhotoItem(ref(false), {
      quality: { tier: "warning", dpi: 72 },
    });

    await nextTick();

    expect(first.find(".quality-badge.warning").exists()).toBe(true);
    expect(second.find(".quality-badge.warning").exists()).toBe(true);
    first.unmount();
    second.unmount();
  });

  test("does not route quality badge keyboard events through photo shortcuts", () => {
    const focus = vi.spyOn(usePhotoFocus(), "focus");
    const wrapper = mountPhotoItem(ref(false), {
      quality: { tier: "warning", dpi: 72 },
    });
    const badge = wrapper.get(".quality-badge").element;

    for (const key of ["Enter", " "]) {
      const event = new KeyboardEvent("keydown", {
        key,
        bubbles: true,
        cancelable: true,
      });

      expect(badge.dispatchEvent(event)).toBe(true);
      expect(event.defaultPrevented).toBe(false);
    }
    expect(focus).not.toHaveBeenCalled();
    wrapper.unmount();
  });
});
