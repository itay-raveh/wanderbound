import { defineComponent, h, ref } from "vue";
import { mountWithPlugins } from "../helpers";
import { provideAlbum } from "@/composables/useAlbum";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { useReplaceExternalMedia } from "@/composables/useReplaceExternalMedia";
import { DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET } from "@/utils/photoQuality";

class PreviewImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  naturalWidth = 1600;
  naturalHeight = 1200;

  set src(_value: string) {
    queueMicrotask(() => this.onload?.());
  }
}

describe("useReplaceExternalMedia", () => {
  afterEach(() => {
    usePhotoFocus().blur();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("cache-busts the current preview URL with the selected media update time", async () => {
    vi.stubGlobal("Image", PreviewImage);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:replacement");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    usePhotoFocus().focus(1, "photo.jpg");
    let result!: ReturnType<typeof useReplaceExternalMedia>;

    const Child = defineComponent({
      setup() {
        result = useReplaceExternalMedia();
        return () => null;
      },
    });
    const Parent = defineComponent({
      setup() {
        provideAlbum({
          albumId: ref("album-1"),
          colors: ref({}),
          media: ref([
            {
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
            },
          ]),
          tripStart: ref("2024-01-01"),
          totalDays: ref(1),
          mediaResolutionWarningPreset: ref(
            DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
          ),
        });
        return () => h(Child);
      },
    });
    mountWithPlugins(Parent);

    const review = await result.prepareDeviceReview(
      new File(["image"], "replacement.jpg", { type: "image/jpeg" }),
    );

    expect(review?.current.previewUrl).toBe(
      "http://localhost:8000/api/v1/albums/album-1/media/photo.jpg?d=2026-05-13T12%3A34%3A56Z",
    );
  });
});
