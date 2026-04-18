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
import { UPGRADE_ERRORS } from "./upgradeErrors";
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

interface MatchSummaryData {
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

type ConfirmAction = "confirm" | "selectMore";

export function useMediaUpgrade() {
  const gp = useGooglePhotos();
  const cache = useQueryCache();

  const phase = ref<UpgradePhase>("idle");
  const progress = ref<UpgradeProgress>({ done: 0, total: 0 });
  const matchSummary = ref<MatchSummaryData | null>(null);
  const errorDetail = ref<string | null>(null);

  let controller: AbortController | null = null;
  let confirmResolve: ((action: ConfirmAction) => void) | null = null;
  let confirmReject: ((reason: Error) => void) | null = null;
  let resetTimer: ReturnType<typeof setTimeout> | null = null;
  let activePopup: Window | null = null;

  // Multi-round state
  const sessionIds: string[] = [];
  const accumulatedMatches: MatchResult[] = [];
  let runningTotalPicked = 0;
  let runningAlreadyUpgraded = 0;

  function reset() {
    progress.value = { done: 0, total: 0 };
    matchSummary.value = null;
    errorDetail.value = null;
    confirmResolve = null;
    confirmReject = null;
    activePopup = null;
    sessionIds.length = 0;
    accumulatedMatches.length = 0;
    runningTotalPicked = 0;
    runningAlreadyUpgraded = 0;
  }

  function openPopup(): Window {
    const width = Math.min(screen.availWidth - 100, 1200);
    const height = Math.min(screen.availHeight - 100, 900);
    const left = ((screen as { availLeft?: number }).availLeft ?? 0) + (screen.availWidth - width) / 2;
    const top = ((screen as { availTop?: number }).availTop ?? 0) + (screen.availHeight - height) / 2;
    const popup = window.open(
      "about:blank",
      "google-photos",
      `width=${width},height=${height},left=${left},top=${top}`,
    );
    if (!popup) throw new Error(UPGRADE_ERRORS.popupBlocked);
    popup.document.title = "Google Photos";
    popup.document.body.style.cssText =
      "font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0;color:#666";
    popup.document.body.textContent = "Loading\u2026";
    return popup;
  }

  function mergeMatches(incoming: MatchResult[]) {
    const byLocalName = new Map<string, MatchResult>();
    for (const m of accumulatedMatches) byLocalName.set(m.local_name, m);
    for (const m of incoming) {
      const prev = byLocalName.get(m.local_name);
      if (!prev || m.distance < prev.distance) {
        byLocalName.set(m.local_name, m);
      }
    }
    accumulatedMatches.length = 0;
    accumulatedMatches.push(...byLocalName.values());
  }

  function buildMergedSummary(): MatchSummaryData {
    return {
      matches: [...accumulatedMatches],
      totalPicked: runningTotalPicked,
      matched: accumulatedMatches.length,
      alreadyUpgraded: runningAlreadyUpgraded,
      unmatched: Math.max(0, runningTotalPicked - accumulatedMatches.length),
    };
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

      // Step 3: Create first picker session
      phase.value = "picking";
      const { sessionId, pickerUri } = await gp.createPickerSession();
      sessionIds.push(sessionId);
      if (signal.aborted) return;
      activePopup.location.href = pickerUri + "/autoclose";

      // Step 4: Poll until ready
      await pollUntilReady(sessionId, signal);
      if (signal.aborted) return;

      // Step 5-6: Match-confirm loop (supports "select more" rounds)
      let currentSessionId = sessionId;
      while (true) {
        phase.value = "preparing";
        progress.value = { done: 0, total: 0 };

        const roundSummary = await runMatchStream(albumId, currentSessionId, signal);
        if (signal.aborted) return;

        if (roundSummary) {
          mergeMatches(roundSummary.matches);
          runningTotalPicked += roundSummary.totalPicked;
          runningAlreadyUpgraded += roundSummary.alreadyUpgraded;
        }

        matchSummary.value = buildMergedSummary();
        phase.value = "confirming";
        const action = await waitForConfirmation(signal);
        if (signal.aborted) return;
        if (action === "confirm") break;

        // "Select More": new session, popup was opened by selectMore()
        const next = await gp.createPickerSession();
        sessionIds.push(next.sessionId);
        currentSessionId = next.sessionId;
        if (signal.aborted) return;

        phase.value = "picking";
        activePopup.location.href = next.pickerUri + "/autoclose";

        await pollUntilReady(currentSessionId, signal);
        if (signal.aborted) return;
      }

      // Step 7: Upgrade
      const toUpgrade = matchSummary.value.matched - matchSummary.value.alreadyUpgraded;
      phase.value = "downloading";
      progress.value = { done: 0, total: toUpgrade };
      await runUpgradeStream(albumId, signal);
      if (signal.aborted) return;

      phase.value = "done";
      await cache.invalidateQueries({ key: queryKeys.media(albumId) });
      scheduleDoneReset();
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      phase.value = "error";
      errorDetail.value = (err as Error).message;
    } finally {
      try { activePopup?.close(); } catch { /* COOP may block */ }
      activePopup = null;
      for (const sid of sessionIds) {
        gp.closeSession(sid).catch(() => {});
      }
      sessionIds.length = 0;
    }
  }

  function confirmUpgrade() {
    // Open popup from the confirm button's click gesture so it's never
    // blocked. Only during onboarding.
    if (phase.value === "onboarding" && !activePopup) {
      try {
        activePopup = openPopup();
      } catch {
        phase.value = "error";
        errorDetail.value = UPGRADE_ERRORS.popupBlocked;
        return;
      }
    }
    confirmResolve?.("confirm");
  }

  function selectMore() {
    // Open popup from the user's click gesture to avoid popup blockers.
    try {
      activePopup = openPopup();
    } catch {
      phase.value = "error";
      errorDetail.value = UPGRADE_ERRORS.popupBlocked;
      return;
    }
    confirmResolve?.("selectMore");
  }

  function cancel() {
    controller?.abort();
    confirmReject?.(new DOMException("Cancelled", "AbortError"));
    try { activePopup?.close(); } catch { /* COOP may block */ }
    activePopup = null;
    for (const sid of sessionIds) {
      gp.closeSession(sid).catch(() => {});
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

  function waitForConfirmation(signal: AbortSignal): Promise<ConfirmAction> {
    return new Promise<ConfirmAction>((resolve, reject) => {
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
    // Google sets COOP on the Picker page, which severs the opener
    // reference and makes popup.closed return true even while the
    // picker is still open.  Rely solely on the backend poll and
    // the cancel button for user-initiated cancellation.
    const deadline = Date.now() + PICKER_TIMEOUT_MS;
    while (!signal.aborted) {
      if (Date.now() > deadline) {
        throw new Error(UPGRADE_ERRORS.selectionTimeout);
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
  ): Promise<MatchSummaryData | null> {
    const { stream } = await matchMedia({
      path: { aid: albumId },
      query: { session_id: sessionId },
      signal,
      sseMaxRetryAttempts: 0,
    });

    let summary: MatchSummaryData | null = null;

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
    signal: AbortSignal,
  ): Promise<void> {
    const { stream } = await upgradeMedia({
      path: { aid: albumId },
      body: {
        session_ids: [...sessionIds],
        matches: accumulatedMatches,
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
      throw new Error(UPGRADE_ERRORS.connectionLost);
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
    selectMore,
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
