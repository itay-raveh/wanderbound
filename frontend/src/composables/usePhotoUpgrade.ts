import { onScopeDispose, ref } from "vue";
import {
  matchPhotos,
  upgradePhotos,
  type MatchResult,
  type UpgradeDownloading,
  type UpgradeDone,
  type UpgradeError,
  type UpgradeMatchSummary,
  type UpgradeMatching,
  type UpgradeReplacing,
} from "@/client";
import { useGooglePhotos } from "./useGooglePhotos";
import { useQueryCache } from "@pinia/colada";
import { queryKeys } from "@/queries/keys";
import { PHOTO_UPGRADE_ONBOARDED_KEY } from "@/utils/storage-keys";

type UpgradePhase =
  | "idle"
  | "onboarding"
  | "authorizing"
  | "picking"
  | "matching"
  | "confirming"
  | "downloading"
  | "done"
  | "error";

interface UpgradeProgress {
  done: number;
  total: number;
}

interface MatchSummary {
  matches: MatchResult[];
  totalMedia: number;
  matched: number;
  unmatched: number;
}

const POLL_INTERVAL_MS = 2000;
const DONE_RESET_MS = 3000;

type MatchEvent =
  | UpgradeMatching
  | UpgradeDownloading
  | UpgradeReplacing
  | UpgradeMatchSummary
  | UpgradeDone
  | UpgradeError;

export function usePhotoUpgrade() {
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

  function reset() {
    progress.value = { done: 0, total: 0 };
    matchSummary.value = null;
    errorDetail.value = null;
    confirmResolve = null;
    confirmReject = null;
  }

  async function start(albumId: string) {
    if (phase.value !== "idle" && phase.value !== "done") return;
    if (resetTimer !== null) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
    reset();
    controller = new AbortController();
    const signal = controller.signal;

    try {
      // Step 1: Onboarding (first time only)
      if (!localStorage.getItem(PHOTO_UPGRADE_ONBOARDED_KEY)) {
        phase.value = "onboarding";
        await waitForConfirmation(signal);
        localStorage.setItem(PHOTO_UPGRADE_ONBOARDED_KEY, "1");
      }

      // Step 2: Authorize if needed
      if (!gp.isConnected.value) {
        phase.value = "authorizing";
        await gp.authorize();
        if (signal.aborted) return;
      }

      // Step 3: Create Picker session and open in new tab
      phase.value = "picking";
      const { sessionId, pickerUri } = await gp.createPickerSession();
      if (signal.aborted) return;
      const pickerTab = window.open(pickerUri + "/autoclose", "_blank");

      // Step 4: Poll until ready
      await pollUntilReady(sessionId, pickerTab, signal);
      if (signal.aborted) return;

      // Step 5: Match photos via SSE
      phase.value = "matching";
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
        phase.value = "done";
        scheduleDoneReset();
        return;
      }
      phase.value = "confirming";
      await waitForConfirmation(signal);
      if (signal.aborted) return;

      // Step 7: Upgrade photos via SSE
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
    }
  }

  function confirmUpgrade() {
    confirmResolve?.();
  }

  function cancel() {
    controller?.abort();
    confirmReject?.(new DOMException("Cancelled", "AbortError"));
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
    pickerTab: Window | null,
    signal: AbortSignal,
  ): Promise<void> {
    while (!signal.aborted) {
      const result = await gp.pollSession(sessionId);
      if (result.ready) return;
      // If the picker tab was closed by user, keep polling briefly in case
      // the session becomes ready from server side
      if (pickerTab?.closed) {
        // Give it a couple more polls
        for (let i = 0; i < 3 && !signal.aborted; i++) {
          await sleep(POLL_INTERVAL_MS, signal);
          const retry = await gp.pollSession(sessionId);
          if (retry.ready) return;
        }
        throw new Error("Picker closed without selecting photos");
      }
      await sleep(POLL_INTERVAL_MS, signal);
    }
  }

  async function runMatchStream(
    albumId: string,
    sessionId: string,
    signal: AbortSignal,
  ): Promise<MatchSummary | null> {
    const { stream } = await matchPhotos({
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
          progress.value = { done: event.done, total: event.total };
          break;
        case "match_summary":
          summary = {
            matches: event.matches,
            totalMedia: event.total_media,
            matched: event.matched,
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
    const { stream } = await upgradePhotos({
      path: { aid: albumId },
      body: {
        session_id: sessionId,
        matches,
      },
      signal,
      sseMaxRetryAttempts: 0,
    });

    for await (const raw of stream) {
      const event = raw as unknown as MatchEvent;
      switch (event.type) {
        case "downloading":
        case "replacing":
          progress.value = { done: event.done, total: event.total };
          break;
        case "done": {
          const { replaced, failed } = event;
          progress.value = { done: replaced, total: replaced + failed };
          break;
        }
        case "error":
          throw new Error(event.detail);
      }
    }
  }

  function scheduleDoneReset() {
    resetTimer = setTimeout(() => {
      phase.value = "idle";
      reset();
      resetTimer = null;
    }, DONE_RESET_MS);
  }

  onScopeDispose(() => cancel());

  return {
    phase,
    progress,
    matchSummary,
    errorDetail,
    googlePhotosState: gp.state,
    start: (albumId: string) => void start(albumId),
    confirmUpgrade,
    cancel,
  };
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}
