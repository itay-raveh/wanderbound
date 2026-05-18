import { defineComponent, h, nextTick, ref, readonly } from "vue";
import { makeAlbumMedia, mountWithPlugins, provideTestAlbum } from "../helpers";
import MediaItem from "@/components/album/MediaItem.vue";
import { STEP_ID_KEY, usePhotoFocus } from "@/composables/usePhotoFocus";
import { PROGRAMMATIC_SCROLL_KEY } from "@/composables/useProgrammaticScroll";

const mutateAsync = vi.fn();
let playSpy: ReturnType<typeof vi.spyOn>;
const MEDIA_UPDATED_AT = "2026-05-13T12:34:56Z";
const MEDIA_UPDATED_AT_PARAM = "2026-05-13T12%3A34%3A56Z";

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
) {
  const Wrapper = defineComponent({
    setup() {
      provideTestAlbum({ media: [media] });
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

    expect(img.attributes("src")).toBe(
      `http://localhost:8000/api/v1/albums/album-1/media/photo.jpg?d=${MEDIA_UPDATED_AT_PARAM}`,
    );

    programmaticScrolling.value = true;
    await nextTick();

    expect(img.attributes("src")).toBe(
      `http://localhost:8000/api/v1/albums/album-1/media/photo.jpg?d=${MEDIA_UPDATED_AT_PARAM}`,
    );
  });

  test("uses updated_at to bust immutable media URLs after same-size replacements", () => {
    const wrapper = mountPhotoItem(
      ref(false),
      { lazy: false },
      { updated_at: "2026-05-13T12:34:56Z" },
    );

    expect(wrapper.get("img").attributes("src")).toBe(
      `http://localhost:8000/api/v1/albums/album-1/media/photo.jpg?d=${MEDIA_UPDATED_AT_PARAM}`,
    );
  });

  test("renders resolution warnings as an icon badge without a tint overlay", () => {
    const wrapper = mountPhotoItem(ref(false), {
      quality: { tier: "warning", dpi: 72 },
    });

    expect(wrapper.find(".quality-overlay").exists()).toBe(false);
    expect(wrapper.find(".quality-badge.warning").exists()).toBe(true);
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
