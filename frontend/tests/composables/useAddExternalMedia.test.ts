import { withSetup } from "../helpers";
import { useAddExternalMedia } from "@/composables/useAddExternalMedia";

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
    googlePhotosMock.authorize.mockReset();
    googlePhotosMock.closeSession.mockReset();
    googlePhotosMock.createPickerSession.mockReset();
    googlePhotosMock.pollSession.mockReset();
    googlePhotosMock.isConnected.value = true;
    googlePhotosMock.state.value = "connected";
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("limits Google import picker sessions to the backend import cap", async () => {
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
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ type: "import_completed", names: ["photo.jpg"] }),
        ),
    );

    const addMedia = withSetup(() => useAddExternalMedia(() => "album-1"));

    await addMedia.importGoogle({ context: "cover" });

    expect(googlePhotosMock.createPickerSession).toHaveBeenCalledWith({
      maxItemCount: 50,
    });
  });
});
