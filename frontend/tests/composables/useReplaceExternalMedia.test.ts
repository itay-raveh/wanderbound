import {
  makeAlbumMedia,
  mockGooglePickerPopup,
  mockReadyGooglePickerSession,
  provideTestAlbum,
  resetGooglePhotosMock,
  withParentSetup,
} from "../helpers";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import {
  replacementInvalidationKeys,
  useReplaceExternalMedia,
} from "@/composables/useReplaceExternalMedia";
import { queryKeys } from "@/queries/keys";

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
  provideTestAlbum({
    media: [makeAlbumMedia()],
  });
}

function mountReplaceExternalMedia() {
  return withParentSetup(provideReplacementAlbum, useReplaceExternalMedia)
    .result;
}

describe("useReplaceExternalMedia", () => {
  afterEach(() => {
    usePhotoFocus().blur();
    resetGooglePhotosMock(googlePhotosMock);
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
    mockReadyGooglePickerSession(googlePhotosMock);
    mockGooglePickerPopup();
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
