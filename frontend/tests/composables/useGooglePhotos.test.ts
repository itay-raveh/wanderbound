import { useGooglePhotos } from "@/composables/useGooglePhotos";
import { UPGRADE_ERRORS } from "@/utils/upgradeErrors";
import { withSetup } from "../helpers";

const api = vi.hoisted(() => ({
  closeSession: vi.fn(),
  createSession: vi.fn(),
  disconnect: vi.fn(),
}));

const currentUser = vi.hoisted(() => ({
  value: {
    google_sub: "google-user",
    google_photos_connected_at: "2026-07-15T23:27:32Z",
  },
}));

vi.mock("@/client", () => api);
vi.mock("@/queries/useUserQuery", () => ({
  useUserQuery: () => ({ user: currentUser }),
}));

class CompletingBroadcastChannel {
  onmessage: (() => void) | null = null;

  constructor() {
    queueMicrotask(() => this.onmessage?.());
  }

  close() {}
}

describe("useGooglePhotos", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    api.createSession.mockReset();
  });

  it("reauthorizes once when picker session creation finds an expired grant", async () => {
    vi.stubGlobal("BroadcastChannel", CompletingBroadcastChannel);
    api.createSession
      .mockResolvedValueOnce({
        data: undefined,
        error: { detail: "Google Photos authorization expired. Please reconnect." },
        response: new Response(null, { status: 401 }),
      })
      .mockResolvedValueOnce({
        data: {
          session_id: "session-2",
          picker_uri: "https://photos.google.com/picker/session-2",
        },
      });
    const popup = {
      closed: false,
      close: vi.fn(),
      location: { href: "about:blank" },
    } as unknown as Window;
    const googlePhotos = withSetup(() => useGooglePhotos());

    const session = await googlePhotos.createPickerSession(
      popup,
      new AbortController().signal,
    );

    expect(popup.location.href).toContain("/api/v1/google-photos/authorize");
    expect(api.createSession).toHaveBeenCalledTimes(2);
    expect(session).toEqual({
      sessionId: "session-2",
      pickerUri: "https://photos.google.com/picker/session-2",
    });
  });

  it("surfaces a connection error when the single retry is unauthorized", async () => {
    vi.stubGlobal("BroadcastChannel", CompletingBroadcastChannel);
    api.createSession.mockResolvedValue({
      data: undefined,
      error: { detail: "Google Photos authorization expired. Please reconnect." },
      response: new Response(null, { status: 401 }),
    });
    const popup = {
      closed: false,
      close: vi.fn(),
      location: { href: "about:blank" },
    } as unknown as Window;
    const googlePhotos = withSetup(() => useGooglePhotos());

    await expect(
      googlePhotos.createPickerSession(
        popup,
        new AbortController().signal,
      ),
    ).rejects.toThrow(UPGRADE_ERRORS.connectionLost);
    expect(api.createSession).toHaveBeenCalledTimes(2);
  });
});
