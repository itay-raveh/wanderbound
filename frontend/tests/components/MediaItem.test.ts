import { defineComponent, h, nextTick, ref, readonly } from "vue";
import { mountWithPlugins } from "../helpers";
import MediaItem from "@/components/album/MediaItem.vue";
import { provideAlbum } from "@/composables/useAlbum";
import { STEP_ID_KEY, usePhotoFocus } from "@/composables/usePhotoFocus";
import { PROGRAMMATIC_SCROLL_KEY } from "@/composables/useProgrammaticScroll";
import { DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET } from "@/utils/photoQuality";

const mutateAsync = vi.fn();
let playSpy: ReturnType<typeof vi.spyOn>;

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

function mountVideoItem() {
  const Wrapper = defineComponent({
    setup() {
      provideAlbum({
        albumId: ref("album-1"),
        colors: ref({}),
        media: ref([
          {
            name: "clip.mp4",
            width: 1920,
            height: 1080,
            type: "video/mp4",
          },
        ]),
        tripStart: ref("2024-01-01"),
        totalDays: ref(1),
        mediaResolutionWarningPreset: ref(
          DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
        ),
      });
      return () => h(MediaItem, { media: "clip.mp4", alt: "Clip" });
    },
  });

  return mountWithPlugins(Wrapper, {
    global: {
      provide: {
        [STEP_ID_KEY as symbol]: 7,
      },
    },
    attachTo: document.body,
  });
}

function mountPhotoItem(
  programmaticScrolling = ref(false),
  props: Record<string, unknown> = {},
) {
  const Wrapper = defineComponent({
    setup() {
      provideAlbum({
        albumId: ref("album-1"),
        colors: ref({}),
        media: ref([{ name: "photo.jpg", width: 1920, height: 1080 }]),
        tripStart: ref("2024-01-01"),
        totalDays: ref(1),
        mediaResolutionWarningPreset: ref(
          DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
        ),
      });
      return () => h(MediaItem, { media: "photo.jpg", alt: "Photo", ...props });
    },
  });

  return mountWithPlugins(Wrapper, {
    global: {
      provide: {
        [STEP_ID_KEY as symbol]: 7,
        [PROGRAMMATIC_SCROLL_KEY as symbol]: readonly(programmaticScrolling),
      },
    },
    attachTo: document.body,
  });
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
    await new Promise((resolve) => setTimeout(resolve));

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
    await new Promise((resolve) => setTimeout(resolve));
    MockIntersectionObserver.instances.at(-1)?.trigger(true);
    await nextTick();
    const img = wrapper.get("img");

    expect(img.attributes("src")).toBe(
      "http://localhost:8000/api/v1/albums/album-1/media/photo.jpg?d=1920x1080",
    );

    programmaticScrolling.value = true;
    await nextTick();

    expect(img.attributes("src")).toBe(
      "http://localhost:8000/api/v1/albums/album-1/media/photo.jpg?d=1920x1080",
    );
  });

  test("renders resolution warnings as an icon badge without a tint overlay", () => {
    const wrapper = mountPhotoItem(ref(false), {
      quality: { tier: "warning", dpi: 72 },
    });

    expect(wrapper.find(".quality-overlay").exists()).toBe(false);
    expect(wrapper.find(".quality-badge.warning").exists()).toBe(true);
  });
});
