import { sleep } from "@/utils/async";

const POLL_INTERVAL_MS = 2000;
const PICKER_TIMEOUT_MS = 10 * 60 * 1000;

interface PickerPopupOptions {
  blockedMessage: string;
  loadingText: string;
}

export function openGooglePhotosPopup({
  blockedMessage,
  loadingText,
}: PickerPopupOptions): Window {
  const width = Math.min(screen.availWidth - 100, 1200);
  const height = Math.min(screen.availHeight - 100, 900);
  const left =
    ((screen as { availLeft?: number }).availLeft ?? 0) +
    (screen.availWidth - width) / 2;
  const top =
    ((screen as { availTop?: number }).availTop ?? 0) +
    (screen.availHeight - height) / 2;
  const popup = window.open(
    "about:blank",
    "google-photos",
    `width=${width},height=${height},left=${left},top=${top}`,
  );
  if (!popup) throw new Error(blockedMessage);
  popup.document.title = "Google Photos";
  popup.document.body.style.cssText =
    "font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0;color:#666";
  popup.document.body.textContent = loadingText;
  return popup;
}

export function closeGooglePhotosPopup(popup: Window | null): void {
  try {
    popup?.close();
  } catch {
    // Cross-origin opener policy can block this.
  }
}

interface PollOptions {
  checkAbortedAfterPoll?: boolean;
}

export async function waitForGooglePhotosSelection(
  pollSession: (sessionId: string) => Promise<{ ready: boolean }>,
  sessionId: string,
  signal: AbortSignal,
  timeoutMessage: string,
  options: PollOptions = {},
): Promise<void> {
  const deadline = Date.now() + PICKER_TIMEOUT_MS;
  while (!signal.aborted) {
    if (Date.now() > deadline) throw new Error(timeoutMessage);
    const result = await pollSession(sessionId);
    if (options.checkAbortedAfterPoll) signal.throwIfAborted();
    if (result.ready) return;
    await sleep(POLL_INTERVAL_MS, signal);
  }
}

export function closeGooglePhotosSessions(
  closeSession: (sessionId: string) => Promise<unknown>,
  sessionIds: Iterable<string>,
): void {
  for (const sessionId of sessionIds) closeSession(sessionId).catch(() => {});
}
