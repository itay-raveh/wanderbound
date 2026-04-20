import { computed } from "vue";
import { UPGRADE_ERRORS } from "./upgradeErrors";
import {
  closeSession as closeSessionApi,
  createSession,
  disconnect as disconnectApi,
  pollSession as pollSessionApi,
} from "@/client";
import { client } from "@/client/client.gen";
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

  async function authorizeInPopup(popup: Window): Promise<void> {
    const nonce = crypto.randomUUID();
    const baseUrl = client.getConfig().baseUrl ?? "";
    popup.location.href = `${baseUrl}/api/v1/google-photos/authorize?nonce=${encodeURIComponent(nonce)}`;

    await new Promise<void>((resolve, reject) => {
      const channel = new BroadcastChannel(`wanderbound-oauth-${nonce}`);

      function cleanup() {
        channel.close();
        clearInterval(closedCheck);
        clearTimeout(timeout);
      }

      channel.onmessage = () => {
        cleanup();
        resolve();
      };

      const closedCheck = setInterval(() => {
        if (popup.closed) {
          cleanup();
          reject(new Error(UPGRADE_ERRORS.authCancelled));
        }
      }, 500);

      const timeout = setTimeout(() => {
        cleanup();
        if (!popup.closed) popup.close();
        reject(new Error(UPGRADE_ERRORS.authTimeout));
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

  async function closePickerSession(sessionId: string): Promise<void> {
    await closeSessionApi({ path: { session_id: sessionId } });
  }

  return {
    state,
    isConnected,
    authorize: authorizeInPopup,
    disconnect: disconnectGooglePhotos,
    createPickerSession,
    pollSession: pollPickerSession,
    closeSession: closePickerSession,
  };
}
