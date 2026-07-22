import {
  mockGooglePickerPopup,
  mockReadyGooglePickerSession,
  resetGooglePhotosMock,
  withSetup,
} from "../helpers";
import { useAddExternalMedia } from "@/composables/useAddExternalMedia";
import { EXTERNAL_MEDIA_IMPORT_MAX_ITEMS } from "@/utils/externalMediaLimits";

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

describe("useAddExternalMedia", () => {
  afterEach(() => {
    resetGooglePhotosMock(googlePhotosMock);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("uses the import contract limit for Google picker sessions", async () => {
    mockReadyGooglePickerSession(googlePhotosMock);
    mockGooglePickerPopup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ type: "import_completed", names: ["photo.jpg"] }),
        ),
    );

    const addMedia = withSetup(() => useAddExternalMedia(() => "album-1"));

    await addMedia.importGoogle({ context: "cover" });

    expect(googlePhotosMock.createPickerSession).toHaveBeenCalledWith(
      expect.anything(),
      expect.any(AbortSignal),
      { maxItemCount: EXTERNAL_MEDIA_IMPORT_MAX_ITEMS },
    );
  });
});
