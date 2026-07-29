import type { useGooglePhotos } from "@/composables/useGooglePhotos";
import {
  closeGooglePhotosPopup,
  closeGooglePhotosSessions,
  openGooglePhotosPopup,
  waitForGooglePhotosSelection,
} from "@/utils/googlePhotosPicker";

type GooglePhotos = ReturnType<typeof useGooglePhotos>;

interface PickerMessages {
  blocked: string;
  loading: string;
  timeout: string;
}

interface PickerOptions {
  maxItemCount?: number;
  checkAbortedAfterPoll?: boolean;
}

export function useGooglePhotosPicker(
  googlePhotos: GooglePhotos,
  messages: PickerMessages,
) {
  let popup: Window | null = null;
  const sessionIds: string[] = [];

  function open(): Window {
    popup = openGooglePhotosPopup({
      blockedMessage: messages.blocked,
      loadingText: messages.loading,
    });
    return popup;
  }

  function currentPopup(): Window {
    return popup && !popup.closed ? popup : open();
  }

  async function authorize(signal: AbortSignal): Promise<void> {
    if (!googlePhotos.isConnected.value) {
      await googlePhotos.authorize(currentPopup(), signal);
    }
  }

  async function pick(
    signal: AbortSignal,
    options: PickerOptions = {},
  ): Promise<string> {
    const activePopup = currentPopup();
    const session = await googlePhotos.createPickerSession(
      activePopup,
      signal,
      { maxItemCount: options.maxItemCount },
    );
    sessionIds.push(session.sessionId);
    activePopup.location.href = `${session.pickerUri}/autoclose`;
    await waitForGooglePhotosSelection(
      googlePhotos.pollSession,
      session.sessionId,
      signal,
      messages.timeout,
      { checkAbortedAfterPoll: options.checkAbortedAfterPoll },
    );
    return session.sessionId;
  }

  function cleanup() {
    closeGooglePhotosPopup(popup);
    popup = null;
    closeGooglePhotosSessions(googlePhotos.closeSession, sessionIds);
    sessionIds.length = 0;
  }

  return {
    state: googlePhotos.state,
    isConnected: googlePhotos.isConnected,
    sessionIds,
    open,
    ensureOpen: currentPopup,
    authorize,
    pick,
    cleanup,
  };
}
