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
import {
  closeGooglePhotosPopup,
  closeGooglePhotosSessions,
  openGooglePhotosPopup,
  waitForGooglePhotosSelection,
} from "@/utils/googlePhotosPicker";

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
  const cache = useQueryCache();
  const onboarded = useLocalStorage<boolean>(
    MEDIA_UPGRADE_ONBOARDED_KEY,
    false,
  );

  const phase = ref<UpgradePhase>("idle");
  const progress = ref<UpgradeProgress>({ done: 0, total: 0 });
  const matchSummary = ref<MatchSummary | null>(null);
  const errorDetail = ref<string | null>(null);

  let controller: AbortController | null = null;
  let confirmResolve: ((action: ConfirmAction) => void) | null = null;
  let confirmReject: ((reason: Error) => void) | null = null;
  let resetTimer: ReturnType<typeof setTimeout> | null = null;
  let activePopup: Window | null = null;

  const sessionIds: string[] = [];
  const accumulator = createMatchAccumulator();

  function reset() {
    progress.value = { done: 0, total: 0 };
    matchSummary.value = null;
    errorDetail.value = null;
    confirmResolve = null;
    confirmReject = null;
    activePopup = null;
    sessionIds.length = 0;
    accumulator.reset();
  }

  function openPopup(): Window {
    return openGooglePhotosPopup({
      blockedMessage: UPGRADE_ERRORS.popupBlocked,
      loadingText: t("upgrade.authorizing"),
    });
  }

  async function start(albumId: string) {
    if (
      phase.value !== "idle" &&
      phase.value !== "done" &&
      phase.value !== "error"
    )
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
      if (!onboarded.value) {
        phase.value = "onboarding";
        await waitForConfirmation(signal);
        onboarded.value = true;
      }

      // For already-onboarded users, open popup from the button click gesture.
      if (!activePopup) activePopup = openPopup();

      // Step 2: Authorize if needed (navigates the existing popup)
      if (!gp.isConnected.value) {
        phase.value = "authorizing";
        await gp.authorize(activePopup, signal);
        if (signal.aborted) return;
      }

      // Step 3: Create first picker session
      phase.value = "picking";
      const { sessionId, pickerUri } = await gp.createPickerSession(
        activePopup,
        signal,
      );
      sessionIds.push(sessionId);
      if (signal.aborted) return;
      activePopup.location.href = pickerUri + "/autoclose";

      // Step 4: Poll until ready
      await waitForGooglePhotosSelection(
        gp.pollSession,
        sessionId,
        signal,
        UPGRADE_ERRORS.selectionTimeout,
      );
      if (signal.aborted) return;

      // Step 5-6: Match-confirm loop (supports "select more" rounds)
      let currentSessionId = sessionId;
      while (true) {
        phase.value = "preparing";
        progress.value = { done: 0, total: 0 };

        const roundSummary = await runMatchStream(
          albumId,
          currentSessionId,
          signal,
        );
        if (signal.aborted) return;

        const newThisRound = roundSummary ? accumulator.merge(roundSummary) : 0;
        matchSummary.value = accumulator.summary(newThisRound);
        phase.value = "confirming";
        const action = await waitForConfirmation(signal);
        if (signal.aborted) return;
        if (action === "confirm") break;
        if (hasReachedGoogleUpgradeSessionLimit(sessionIds)) {
          throw new Error(UPGRADE_ERRORS.tooManySelectionRounds);
        }

        // "Select More": new session, popup was opened by selectMore()
        const next = await gp.createPickerSession(activePopup, signal);
        sessionIds.push(next.sessionId);
        currentSessionId = next.sessionId;
        if (signal.aborted) return;

        phase.value = "picking";
        activePopup.location.href = next.pickerUri + "/autoclose";

        await waitForGooglePhotosSelection(
          gp.pollSession,
          currentSessionId,
          signal,
          UPGRADE_ERRORS.selectionTimeout,
        );
        if (signal.aborted) return;
      }

      // Step 7: Upgrade
      const toUpgrade =
        matchSummary.value.matched - matchSummary.value.alreadyUpgraded;
      phase.value = "downloading";
      progress.value = { done: 0, total: toUpgrade };
      await runUpgradeStream(albumId, signal);
      if (signal.aborted) return;

      phase.value = "done";
      await Promise.all(
        mediaUpgradeInvalidationKeys(albumId).map((key) =>
          cache.invalidateQueries(invalidateAlbumKey(key)),
        ),
      );
      scheduleDoneReset();
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      phase.value = "error";
      errorDetail.value = (err as Error).message;
    } finally {
      closeGooglePhotosPopup(activePopup);
      activePopup = null;
      closeGooglePhotosSessions(gp.closeSession, sessionIds);
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
      activePopup = openPopup();
    } catch {
      confirmReject?.(new Error(UPGRADE_ERRORS.popupBlocked));
      return;
    }
    confirmResolve?.("selectMore");
  }

  function cancel() {
    controller?.abort();
    confirmReject?.(new DOMException("Cancelled", "AbortError"));
    closeGooglePhotosPopup(activePopup);
    closeGooglePhotosSessions(gp.closeSession, sessionIds);
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
          if (event.phase === "preparing") phase.value = "preparing";
          else phase.value = "matching";
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
      phase.value = "idle";
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
    if (!busyPhases.has(phase.value)) return;
    const handler = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", handler);
    onCleanup(() => window.removeEventListener("beforeunload", handler));
  });

  onScopeDispose(cancel);

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
  };
}

function mediaUpgradeInvalidationKeys(aid: string) {
  return [
    queryKeys.album(aid),
    queryKeys.media(aid),
    queryKeys.printBundles(aid),
  ];
}
