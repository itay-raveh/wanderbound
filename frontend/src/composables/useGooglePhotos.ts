import { computed } from "vue";
import {
  authorize,
  createSession,
  disconnect as disconnectApi,
  pollSession as pollSessionApi,
} from "@/client";
import { useUserQuery } from "@/queries/useUserQuery";
import { useQueryCache } from "@pinia/colada";
import { queryKeys } from "@/queries/keys";

type GooglePhotosState = "unavailable" | "disconnected" | "connected";

export function useGooglePhotos() {
  const { user } = useUserQuery();
  const cache = useQueryCache();

  const state = computed<GooglePhotosState>(() => {
    if (!user.value?.google_sub) return "unavailable";
    if (!user.value.google_photos_connected_at) return "disconnected";
    return "connected";
  });

  const isConnected = computed(() => state.value === "connected");

  async function authorizeGooglePhotos(): Promise<void> {
    const { data } = await authorize();
    if (!data?.authorization_url) throw new Error("No authorization URL");

    const width = 600;
    const height = 700;
    const left = window.screenX + (window.innerWidth - width) / 2;
    const top = window.screenY + (window.innerHeight - height) / 2;
    const popup = window.open(
      data.authorization_url,
      "google-photos-auth",
      `width=${width},height=${height},left=${left},top=${top}`,
    );
    if (!popup) throw new Error("Popup blocked");

    await new Promise<void>((resolve, reject) => {
      const interval = setInterval(() => {
        try {
          if (popup.closed) {
            clearInterval(interval);
            clearTimeout(timeout);
            resolve();
          }
        } catch {
          // Cross-origin - popup still open
        }
      }, 500);
      const timeout = setTimeout(() => {
        clearInterval(interval);
        if (!popup.closed) popup.close();
        reject(new Error("Authorization timed out"));
      }, 5 * 60 * 1000);
    });

    await cache.invalidateQueries({ key: queryKeys.user() });
  }

  async function disconnectGooglePhotos(): Promise<void> {
    await disconnectApi();
    await cache.invalidateQueries({ key: queryKeys.user() });
  }

  async function createPickerSession(): Promise<{
    sessionId: string;
    pickerUri: string;
  }> {
    const { data } = await createSession();
    if (!data) throw new Error("Failed to create picker session");
    return { sessionId: data.session_id, pickerUri: data.picker_uri };
  }

  async function pollPickerSession(
    sessionId: string,
  ): Promise<{ ready: boolean }> {
    const { data } = await pollSessionApi({
      path: { session_id: sessionId },
    });
    if (!data) throw new Error("Failed to poll session");
    return { ready: data.ready };
  }

  return {
    state,
    isConnected,
    authorize: authorizeGooglePhotos,
    disconnect: disconnectGooglePhotos,
    createPickerSession,
    pollSession: pollPickerSession,
  };
}
