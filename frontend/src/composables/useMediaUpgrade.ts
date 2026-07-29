import { onScopeDispose, ref, watchEffect } from "vue";
import { useLocalStorage } from "@vueuse/core";
import { t } from "@/i18n";
import {
  matchMedia,
  upgradeMedia,
  type DownloadInProgress,
  type MatchCompleted,
  type MatchInProgress,
  type UpgradeCompleted,
  type UpgradeFailed,
} from "@/client";
import { useGooglePhotos } from "./useGooglePhotos";
import { useGooglePhotosPicker } from "./useGooglePhotosPicker";
import { useMediaOperationState } from "./useMediaOperationState";
import { UPGRADE_ERRORS, type UpgradeErrorKey } from "@/utils/upgradeErrors";
import {
  createMatchAccumulator,
  type MatchRound,
  type MatchSummary,
} from "./matchAccumulator";
import { useQueryCache } from "@pinia/colada";
import { invalidateAlbumKey, queryKeys } from "@/queries/keys";
import { MEDIA_UPGRADE_ONBOARDED_KEY } from "@/utils/storage-keys";
import {
  GOOGLE_UPGRADE_MAX_MATCHES,
  GOOGLE_UPGRADE_MAX_SESSION_IDS,
} from "@/utils/externalMediaLimits";

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

const DONE_RESET_MS = 3000;

type MatchEvent =
  | MatchInProgress
  | DownloadInProgress
  | MatchCompleted
  | UpgradeCompleted
  | UpgradeFailed;

type ConfirmAction = "confirm" | "selectMore";

function hasReachedGoogleUpgradeSessionLimit(
  sessionIds: readonly unknown[],
): boolean {
  return sessionIds.length >= GOOGLE_UPGRADE_MAX_SESSION_IDS;
}

function googleUpgradeRequestLimitError(
  sessionIds: readonly unknown[],
  matches: readonly unknown[],
): UpgradeErrorKey | null {
  if (sessionIds.length > GOOGLE_UPGRADE_MAX_SESSION_IDS) {
    return UPGRADE_ERRORS.tooManySelectionRounds;
  }
  if (matches.length > GOOGLE_UPGRADE_MAX_MATCHES) {
    return UPGRADE_ERRORS.tooManyMatches;
  }
  return null;
}

export function useMediaUpgrade() {
  const gp = useGooglePhotos();
  const operation = useMediaOperationState<UpgradePhase>("idle", "error");
  const picker = useGooglePhotosPicker(gp, {
    blocked: UPGRADE_ERRORS.popupBlocked,
    loading: t("upgrade.authorizing"),
    timeout: UPGRADE_ERRORS.selectionTimeout,
  });
  const cache = useQueryCache();
  const onboarded = useLocalStorage<boolean>(
    MEDIA_UPGRADE_ONBOARDED_KEY,
    false,
  );

  const progress = ref<UpgradeProgress>({ done: 0, total: 0 });
  const matchSummary = ref<MatchSummary | null>(null);

  let confirmResolve: ((action: ConfirmAction) => void) | null = null;
  let confirmReject: ((reason: Error) => void) | null = null;
  let resetTimer: ReturnType<typeof setTimeout> | null = null;

  const { sessionIds } = picker;
  const accumulator = createMatchAccumulator();

  function reset() {
    operation.abort();
    operation.clearError();
    progress.value = { done: 0, total: 0 };
    matchSummary.value = null;
    confirmResolve = null;
    confirmReject = null;
    picker.cleanup();
    accumulator.reset();
  }

  async function start(albumId: string) {
    if (
      operation.phase.value !== "idle" &&
      operation.phase.value !== "done" &&
      operation.phase.value !== "error"
    )
      return;

    if (resetTimer !== null) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
    reset();
    const signal = operation.begin();

    try {
      // Step 1: Onboarding (first time only)
      if (!onboarded.value) {
        operation.phase.value = "onboarding";
        await waitForConfirmation(signal);
        onboarded.value = true;
      }

      // For already-onboarded users, open popup from the button click gesture.
      picker.ensureOpen();

      // Step 2: Authorize if needed (navigates the existing popup)
      if (!picker.isConnected.value) {
        operation.phase.value = "authorizing";
        await picker.authorize(signal);
        if (signal.aborted) return;
      }

      // Step 3: Create first picker session
      operation.phase.value = "picking";
      const sessionId = await picker.pick(signal);
      if (signal.aborted) return;

      // Step 5-6: Match-confirm loop (supports "select more" rounds)
      let currentSessionId = sessionId;
      while (true) {
        operation.phase.value = "preparing";
        progress.value = { done: 0, total: 0 };

        const roundSummary = await runMatchStream(
          albumId,
          currentSessionId,
          signal,
        );
        if (signal.aborted) return;

        const newThisRound = roundSummary ? accumulator.merge(roundSummary) : 0;
        matchSummary.value = accumulator.summary(newThisRound);
        operation.phase.value = "confirming";
        const action = await waitForConfirmation(signal);
        if (signal.aborted) return;
        if (action === "confirm") break;
        if (hasReachedGoogleUpgradeSessionLimit(sessionIds)) {
          throw new Error(UPGRADE_ERRORS.tooManySelectionRounds);
        }

        // "Select More": new session, popup was opened by selectMore()
        operation.phase.value = "picking";
        currentSessionId = await picker.pick(signal);
        if (signal.aborted) return;
      }

      // Step 7: Upgrade
      const toUpgrade =
        matchSummary.value.matched - matchSummary.value.alreadyUpgraded;
      operation.phase.value = "downloading";
      progress.value = { done: 0, total: toUpgrade };
      await runUpgradeStream(albumId, signal);
      if (signal.aborted) return;

      operation.phase.value = "done";
      await Promise.all(
        mediaUpgradeInvalidationKeys(albumId).map((key) =>
          cache.invalidateQueries(invalidateAlbumKey(key)),
        ),
      );
      scheduleDoneReset();
    } catch (err) {
      operation.fail(err, UPGRADE_ERRORS.connectionLost);
    } finally {
      picker.cleanup();
    }
  }

  function confirmUpgrade() {
    // Open popup from the confirm button's click gesture so it's never
    // blocked. Only during onboarding.
    if (operation.phase.value === "onboarding") {
      try {
        picker.ensureOpen();
      } catch {
        confirmReject?.(new Error(UPGRADE_ERRORS.popupBlocked));
        return;
      }
    }
    confirmResolve?.("confirm");
  }

  function selectMore() {
    if (hasReachedGoogleUpgradeSessionLimit(sessionIds)) {
      confirmReject?.(new Error(UPGRADE_ERRORS.tooManySelectionRounds));
      return;
    }
    try {
      picker.open();
    } catch {
      confirmReject?.(new Error(UPGRADE_ERRORS.popupBlocked));
      return;
    }
    confirmResolve?.("selectMore");
  }

  function cancel() {
    operation.abort();
    confirmReject?.(new DOMException("Cancelled", "AbortError"));
    picker.cleanup();
    if (resetTimer !== null) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
    operation.phase.value = "idle";
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

  async function runMatchStream(
    albumId: string,
    sessionId: string,
    signal: AbortSignal,
  ): Promise<MatchRound | null> {
    const { stream } = await matchMedia({
      path: { aid: albumId },
      query: { session_id: sessionId },
      signal,
      sseMaxRetryAttempts: 0,
    });

    let round: MatchRound | null = null;
    let receivedTerminal = false;

    for await (const raw of stream) {
      const event = raw as unknown as MatchEvent;
      switch (event.type) {
        case "match_in_progress":
          if (event.phase === "preparing") operation.phase.value = "preparing";
          else operation.phase.value = "matching";
          progress.value = { done: event.done, total: event.total };
          break;
        case "match_completed":
          round = {
            matches: event.matches,
            totalPicked: event.total_picked,
          };
          receivedTerminal = true;
          break;
        case "upgrade_failed":
          throw new Error(event.detail);
      }
    }

    if (!receivedTerminal) throw new Error(UPGRADE_ERRORS.connectionLost);
    return round;
  }

  async function runUpgradeStream(
    albumId: string,
    signal: AbortSignal,
  ): Promise<void> {
    const limitError = googleUpgradeRequestLimitError(
      sessionIds,
      accumulator.matches,
    );
    if (limitError) throw new Error(limitError);

    const { stream } = await upgradeMedia({
      path: { aid: albumId },
      body: {
        session_ids: [...sessionIds],
        matches: [...accumulator.matches],
      },
      signal,
      sseMaxRetryAttempts: 0,
    });

    let receivedTerminal = false;

    for await (const raw of stream) {
      const event = raw as unknown as MatchEvent;
      switch (event.type) {
        case "download_in_progress":
          progress.value = { done: event.done, total: event.total };
          break;
        case "upgrade_completed": {
          const { replaced, skipped, failed } = event;
          progress.value = {
            done: replaced,
            total: replaced + skipped + failed,
            skipped,
          };
          receivedTerminal = true;
          break;
        }
        case "upgrade_failed":
          throw new Error(event.detail);
      }
    }

    if (!receivedTerminal) {
      throw new Error(UPGRADE_ERRORS.connectionLost);
    }
  }

  function scheduleDoneReset() {
    resetTimer = setTimeout(() => {
      operation.phase.value = "idle";
      reset();
      resetTimer = null;
    }, DONE_RESET_MS);
  }

  // Warn before navigating away while a picker is open or the pipeline is running.
  // `picking` is included so a mid-picker refresh still triggers the prompt -
  // without it the backend picker session would be orphaned (finally never runs).
  const busyPhases: ReadonlySet<UpgradePhase> = new Set([
    "picking",
    "preparing",
    "matching",
    "downloading",
  ]);
  watchEffect((onCleanup) => {
    if (!busyPhases.has(operation.phase.value)) return;
    const handler = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", handler);
    onCleanup(() => window.removeEventListener("beforeunload", handler));
  });

  onScopeDispose(cancel);

  return {
    phase: operation.phase,
    progress,
    matchSummary,
    errorDetail: operation.errorDetail,
    googlePhotosState: picker.state,
    start: (albumId: string) => void start(albumId),
    confirmUpgrade,
    selectMore,
    cancel,
  };
}

function mediaUpgradeInvalidationKeys(aid: string) {
  return [
    queryKeys.album(aid),
    queryKeys.media(aid),
    queryKeys.printBundles(aid),
  ];
}
