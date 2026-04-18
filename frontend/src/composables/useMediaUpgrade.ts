import { onScopeDispose, ref, watch } from "vue";
import {
  matchMedia,
  upgradeMedia,
  type MatchResult,
  type UpgradeDownloading,
  type UpgradeDone,
  type UpgradeError,
  type UpgradeMatchSummary,
  type UpgradeMatching,
} from "@/client";
import { useGooglePhotos } from "./useGooglePhotos";
import { useQueryCache } from "@pinia/colada";
import { queryKeys } from "@/queries/keys";
import { MEDIA_UPGRADE_ONBOARDED_KEY } from "@/utils/storage-keys";

type UpgradePhase =
  | "idle"
  | "onboarding"
  | "authorizing"
  | "picking"
  | "preparing"
  | "matching"
  | "confirming"
  | "downloading"
  | "done"
  | "error";

interface UpgradeProgress {
  done: number;
  total: number;
  skipped?: number;
}

interface MatchSummary {
  matches: MatchResult[];
  totalPicked: number;
  matched: number;
  alreadyUpgraded: number;
  unmatched: number;
}

const POLL_INTERVAL_MS = 2000;
const PICKER_TIMEOUT_MS = 10 * 60 * 1000;
const DONE_RESET_MS = 3000;

type MatchEvent =
  | UpgradeMatching
  | UpgradeDownloading
  | UpgradeMatchSummary
  | UpgradeDone
  | UpgradeError;

export function useMediaUpgrade() {
  const gp = useGooglePhotos();
  const cache = useQueryCache();

  const phase = ref<UpgradePhase>("idle");
  const progress = ref<UpgradeProgress>({ done: 0, total: 0 });
  const matchSummary = ref<MatchSummary | null>(null);
  const errorDetail = ref<string | null>(null);

  let controller: AbortController | null = null;
  let confirmResolve: (() => void) | null = null;
  let confirmReject: ((reason: Error) => void) | null = null;
  let resetTimer: ReturnType<typeof setTimeout> | null = null;
  let activeSessionId: string | null = null;
  let activePopup: Window | null = null;

  function reset() {
    progress.value = { done: 0, total: 0 };
    matchSummary.value = null;
    errorDetail.value = null;
    confirmResolve = null;
    confirmReject = null;
    activeSessionId = null;
    activePopup = null;
  }

  function openPopup(): Window {
    const width = Math.min(screen.availWidth - 100, 1200);
    const height = Math.min(screen.availHeight - 100, 900);
    const left = screen.availLeft + (screen.availWidth - width) / 2;
    const top = screen.availTop + (screen.availHeight - height) / 2;
    const popup = window.open(
      "about:blank",
      "google-photos",
      `width=${width},height=${height},left=${left},top=${top}`,
    );
    if (!popup) throw new Error("Popup blocked");
    popup.document.title = "Google Photos";
    popup.document.body.style.cssText =
      "font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0;color:#666";
    popup.document.body.textContent = "Loading\u2026";
    return popup;
  }

  async function start(albumId: string) {
    if (phase.value !== "idle" && phase.value !== "done" && phase.value !== "error")
      return;
    if (resetTimer !== null) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
    reset();
    controller = new AbortController();
    const signal = controller.signal;

    try {
      // Step 1: Onboarding (first time only)
      // The popup is opened inside confirmUpgrade() from the confirm
      // button's click handler, preserving the user gesture.
      if (!localStorage.getItem(MEDIA_UPGRADE_ONBOARDED_KEY)) {
        phase.value = "onboarding";
        await waitForConfirmation(signal);
        localStorage.setItem(MEDIA_UPGRADE_ONBOARDED_KEY, "1");
      }

      // For already-onboarded users, open popup from the button click gesture.
      if (!activePopup) activePopup = openPopup();

      // Step 2: Authorize if needed (navigates the existing popup)
      if (!gp.isConnected.value) {
        phase.value = "authorizing";
        await gp.authorize(activePopup);
        if (signal.aborted) return;
      }

      // Step 3: Create Picker session, navigate same popup
      phase.value = "picking";
      const { sessionId, pickerUri } = await gp.createPickerSession();
      activeSessionId = sessionId;
      if (signal.aborted) return;
      activePopup.location.href = pickerUri + "/autoclose";

      // Step 4: Poll until ready
      await pollUntilReady(sessionId, signal);
      if (signal.aborted) return;

      // Step 5: Match media via SSE
      phase.value = "preparing";
      progress.value = { done: 0, total: 0 };
      const summary = await runMatchStream(albumId, sessionId, signal);
      if (signal.aborted) return;
      if (!summary) {
        phase.value = "error";
        errorDetail.value = "Matching returned no results";
        return;
      }

      // Step 6: Show summary, wait for confirmation
      matchSummary.value = summary;
      if (summary.matched === 0) {
        if (activeSessionId) {
          gp.closeSession(activeSessionId).catch(() => {});
          activeSessionId = null;
        }
        phase.value = "done";
        scheduleDoneReset();
        return;
      }
      phase.value = "confirming";
      await waitForConfirmation(signal);
      if (signal.aborted) return;

      // Step 7: Upgrade media via SSE
      phase.value = "downloading";
      progress.value = { done: 0, total: summary.matched };
      await runUpgradeStream(albumId, sessionId, summary.matches, signal);
      if (signal.aborted) return;

      phase.value = "done";
      await cache.invalidateQueries({ key: queryKeys.media(albumId) });
      scheduleDoneReset();
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      phase.value = "error";
      errorDetail.value = (err as Error).message;
    } finally {
      if (activePopup && !activePopup.closed) activePopup.close();
      activePopup = null;
    }
  }

  function confirmUpgrade() {
    // Open popup from the confirm button's click gesture so it's never
    // blocked.  Only during onboarding - the match-summary confirm
    // doesn't need a popup.
    if (phase.value === "onboarding" && !activePopup) {
      activePopup = openPopup();
    }
    confirmResolve?.();
  }

  function cancel() {
    controller?.abort();
    confirmReject?.(new DOMException("Cancelled", "AbortError"));
    if (activePopup && !activePopup.closed) activePopup.close();
    activePopup = null;
    if (activeSessionId) {
      gp.closeSession(activeSessionId).catch(() => {});
    }
    confirmResolve = null;
    confirmReject = null;
    if (resetTimer !== null) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
    phase.value = "idle";
    reset();
  }

  function waitForConfirmation(signal: AbortSignal): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      if (signal.aborted) {
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      confirmResolve = resolve;
      confirmReject = reject;
      signal.addEventListener(
        "abort",
        () => reject(new DOMException("Aborted", "AbortError")),
        { once: true },
      );
    });
  }

  async function pollUntilReady(
    sessionId: string,
    signal: AbortSignal,
  ): Promise<void> {
    // Google sets COOP on the Picker page, so popup.closed throws
    // a cross-origin error once COOP activates. We still check it
    // because it works during the initial redirect and after the
    // user closes the popup, catching the common "changed my mind"
    // case instead of forcing a 10-minute timeout.
    const deadline = Date.now() + PICKER_TIMEOUT_MS;
    while (!signal.aborted) {
      if (Date.now() > deadline) {
        throw new Error("Photo selection timed out");
      }
      try {
        if (activePopup?.closed) {
          throw new Error("Photo selection cancelled");
        }
      } catch {
        // COOP blocks cross-origin property access - ignore.
      }
      const result = await gp.pollSession(sessionId);
      if (result.ready) return;
      await sleep(POLL_INTERVAL_MS, signal);
    }
  }

  async function runMatchStream(
    albumId: string,
    sessionId: string,
    signal: AbortSignal,
  ): Promise<MatchSummary | null> {
    const { stream } = await matchMedia({
      path: { aid: albumId },
      query: { session_id: sessionId },
      signal,
      sseMaxRetryAttempts: 0,
    });

    let summary: MatchSummary | null = null;

    for await (const raw of stream) {
      const event = raw as unknown as MatchEvent;
      switch (event.type) {
        case "matching":
          if (event.phase === "preparing") phase.value = "preparing";
          else phase.value = "matching";
          progress.value = { done: event.done, total: event.total };
          break;
        case "match_summary":
          summary = {
            matches: event.matches,
            totalPicked: event.total_picked,
            matched: event.matched,
            alreadyUpgraded: event.already_upgraded,
            unmatched: event.unmatched,
          };
          break;
        case "error":
          throw new Error(event.detail);
      }
    }

    return summary;
  }

  async function runUpgradeStream(
    albumId: string,
    sessionId: string,
    matches: MatchResult[],
    signal: AbortSignal,
  ): Promise<void> {
    const { stream } = await upgradeMedia({
      path: { aid: albumId },
      body: {
        session_id: sessionId,
        matches,
      },
      signal,
      sseMaxRetryAttempts: 0,
    });

    let receivedTerminal = false;

    for await (const raw of stream) {
      const event = raw as unknown as MatchEvent;
      switch (event.type) {
        case "downloading":
          progress.value = { done: event.done, total: event.total };
          break;
        case "done": {
          const { replaced, skipped, failed } = event;
          progress.value = {
            done: replaced,
            total: replaced + skipped + failed,
            skipped,
          };
          receivedTerminal = true;
          break;
        }
        case "error":
          throw new Error(event.detail);
      }
    }

    if (!receivedTerminal) {
      throw new Error("Connection lost during upgrade");
    }
  }

  function scheduleDoneReset() {
    resetTimer = setTimeout(() => {
      phase.value = "idle";
      reset();
      resetTimer = null;
    }, DONE_RESET_MS);
  }

  // Warn the user before navigating away during active operations.
  const busyPhases: ReadonlySet<UpgradePhase> = new Set([
    "preparing",
    "matching",
    "downloading",
  ]);
  function onBeforeUnload(e: BeforeUnloadEvent) {
    e.preventDefault();
  }
  watch(phase, (cur, prev) => {
    if (busyPhases.has(cur) && !busyPhases.has(prev)) {
      window.addEventListener("beforeunload", onBeforeUnload);
    } else if (!busyPhases.has(cur) && busyPhases.has(prev)) {
      window.removeEventListener("beforeunload", onBeforeUnload);
    }
  });

  onScopeDispose(() => {
    window.removeEventListener("beforeunload", onBeforeUnload);
    cancel();
  });

  return {
    phase,
    progress,
    matchSummary,
    errorDetail,
    googlePhotosState: gp.state,
    start: (albumId: string) => void start(albumId),
    confirmUpgrade,
    cancel,
    disconnect: gp.disconnect,
  };
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}
