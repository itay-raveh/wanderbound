import { ref } from "vue";
import { withParentSetup } from "../helpers";
import { provideAlbum } from "@/composables/useAlbum";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import {
  replacementInvalidationKeys,
  useReplaceExternalMedia,
} from "@/composables/useReplaceExternalMedia";
import { queryKeys } from "@/queries/keys";
import { DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET } from "@/utils/photoQuality";

const googlePhotosMock = vi.hoisted(() => ({
  authorize: vi.fn(),
  closeSession: vi.fn(),
  createPickerSession: vi.fn(),
  isConnected: { value: true },
  pollSession: vi.fn(),
  state: { value: "connected" },
}));

vi.mock("@/composables/useGooglePhotos", () => ({
  useGooglePhotos: () => googlePhotosMock,
}));

class PreviewImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  naturalWidth = 1600;
  naturalHeight = 1200;

  set src(_value: string) {
    queueMicrotask(() => this.onload?.());
  }
}

function provideReplacementAlbum() {
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
    mediaResolutionWarningPreset: ref(DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET),
  });
}

function mountReplaceExternalMedia() {
  return withParentSetup(provideReplacementAlbum, useReplaceExternalMedia)
    .result;
}

describe("useReplaceExternalMedia", () => {
  afterEach(() => {
    usePhotoFocus().blur();
    googlePhotosMock.authorize.mockReset();
    googlePhotosMock.closeSession.mockReset();
    googlePhotosMock.createPickerSession.mockReset();
    googlePhotosMock.pollSession.mockReset();
    googlePhotosMock.isConnected.value = true;
    googlePhotosMock.state.value = "connected";
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("cache-busts the current preview URL with the selected media update time", async () => {
    vi.stubGlobal("Image", PreviewImage);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:replacement");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    usePhotoFocus().focus(1, "photo.jpg");
    const result = mountReplaceExternalMedia();

    const review = await result.prepareDeviceReview(
      new File(["image"], "replacement.jpg", { type: "image/jpeg" }),
    );

    expect(review?.current.previewUrl).toBe(
      "http://localhost:8000/api/v1/albums/album-1/media/photo.jpg?d=2026-05-13T12%3A34%3A56Z",
    );
  });

  it("limits Google replacement picker sessions to one item", async () => {
    googlePhotosMock.createPickerSession.mockResolvedValue({
      sessionId: "session-1",
      pickerUri: "https://photos.google.com/picker/session-1",
    });
    googlePhotosMock.pollSession.mockResolvedValue({ ready: true });
    googlePhotosMock.closeSession.mockResolvedValue(undefined);

    const popup = {
      close: vi.fn(),
      document: {
        body: { style: {}, textContent: "" },
        title: "",
      },
      location: { href: "" },
    };
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 200 })),
    );

    usePhotoFocus().focus(1, "photo.jpg");
    const result = mountReplaceExternalMedia();

    await expect(result.replaceFromGoogle()).resolves.toBe("photo.jpg");

    expect(googlePhotosMock.createPickerSession).toHaveBeenCalledWith({
      maxItemCount: 1,
    });
  });

  it("invalidates print bundle after replacements", () => {
    expect(replacementInvalidationKeys("album-1")).toEqual([
      queryKeys.album("album-1"),
      queryKeys.media("album-1"),
      queryKeys.steps("album-1"),
      queryKeys.printBundle("album-1"),
    ]);
  });
});
