import { undoReplacement } from "@/client";
import type { ReplacementResult } from "@/composables/useReplaceExternalMedia";
import { invalidateAlbumKey, queryKeys } from "@/queries/keys";
import { useQueryCache } from "@pinia/colada";
import { Notify, format } from "quasar";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";

interface UndoState {
  aid: string;
  mediaName: string;
  expiresAt: number;
  pending: boolean;
}

const UNDO_WINDOW_MS = 5 * 60 * 1000;
const { humanStorageSize } = format;
const undoState = ref<UndoState | null>(null);

let expireTimer: ReturnType<typeof setTimeout> | null = null;
let updateReplacementToast: ReturnType<typeof Notify.create> | null = null;

function resetUndoState() {
  undoState.value = null;
  if (expireTimer !== null) {
    clearTimeout(expireTimer);
    expireTimer = null;
  }
}

function clearUndoState() {
  resetUndoState();
  updateReplacementToast?.();
  updateReplacementToast = null;
}

export function useMediaUndo(albumId: () => string) {
  const cache = useQueryCache();
  const { locale, t } = useI18n();

  const currentUndo = computed(() => {
    const state = undoState.value;
    if (!state || state.aid !== albumId()) return null;
    return state;
  });

  function dismissAction() {
    return {
      icon: "close",
      color: "white",
      "aria-label": t("common.close"),
      handler: clearUndoState,
    };
  }

  function keepReplacementAction() {
    return {
      label: t("externalMedia.undo.keep"),
      color: "white",
      handler: clearUndoState,
    };
  }

  function startReplacement() {
    clearUndoState();
    updateReplacementToast = Notify.create({
      group: false,
      timeout: 0,
      type: "info",
      spinner: true,
      message: t("externalMedia.replace.replacing"),
    });
  }

  function failReplacement(message: string) {
    resetUndoState();
    const failure = {
      timeout: 5000,
      type: "negative" as const,
      spinner: false,
      message,
      actions: [dismissAction()],
    };
    if (updateReplacementToast) updateReplacementToast(failure);
    else
      updateReplacementToast = Notify.create({
        ...failure,
        group: false,
      });
  }

  function rememberReplacement(result: ReplacementResult) {
    resetUndoState();
    undoState.value = {
      aid: albumId(),
      mediaName: result.mediaName,
      expiresAt: Date.now() + UNDO_WINDOW_MS,
      pending: false,
    };
    showReplacementReceipt(result);
    expireTimer = setTimeout(clearUndoState, UNDO_WINDOW_MS);
  }

  function showReplacementReceipt(result: ReplacementResult) {
    const before = formatReceiptSide(result.previous, locale.value);
    const after = formatReceiptSide(result.replacement, locale.value);
    const success = {
      timeout: UNDO_WINDOW_MS,
      type: "positive" as const,
      spinner: false,
      message: t("externalMedia.replace.done"),
      caption: t("externalMedia.replace.receipt", { before, after }),
      actions: [undoAction(), keepReplacementAction()],
    };
    if (updateReplacementToast) updateReplacementToast(success);
    else
      updateReplacementToast = Notify.create({
        ...success,
        group: false,
      });
  }

  function undoAction(label = t("externalMedia.undo.action")) {
    return {
      label,
      color: "white",
      noDismiss: true,
      handler: () => {
        void undo();
      },
    };
  }

  async function undo() {
    const state = currentUndo.value;
    if (!state || state.pending) return;
    state.pending = true;
    updateReplacementToast?.({
      timeout: 0,
      type: "info",
      spinner: true,
      message: t("externalMedia.undo.undoing"),
      caption: undefined,
      actions: [],
    });
    try {
      await undoReplacement({
        path: { aid: state.aid, media_name: state.mediaName },
      });
      await Promise.all(
        mediaUndoInvalidationKeys(state.aid).map((key) =>
          cache.invalidateQueries(invalidateAlbumKey(key)),
        ),
      );
      resetUndoState();
      updateReplacementToast?.({
        timeout: 5000,
        type: "positive",
        spinner: false,
        message: t("externalMedia.undo.done"),
        actions: [dismissAction()],
      });
      updateReplacementToast = null;
    } catch {
      state.pending = false;
      updateReplacementToast?.({
        timeout: 0,
        type: "negative",
        spinner: false,
        message: t("externalMedia.undo.failed"),
        caption: undefined,
        actions: [
          undoAction(t("externalMedia.undo.retry")),
          keepReplacementAction(),
        ],
      });
    }
  }

  return {
    cancelReplacement: clearUndoState,
    currentUndo,
    failReplacement,
    startReplacement,
    rememberReplacement,
    undo,
    clearUndoState,
  };
}

function formatReceiptSide(
  metadata: ReplacementResult["previous"],
  locale: string,
) {
  const dimensions = `${formatNumber(metadata.width, locale)} × ${formatNumber(metadata.height, locale)}`;
  return `\u2066${dimensions} · ${humanStorageSize(metadata.byteSize)}\u2069`;
}

function formatNumber(value: number, locale: string) {
  return new Intl.NumberFormat(locale).format(value);
}

export function mediaUndoInvalidationKeys(aid: string) {
  return [
    queryKeys.album(aid),
    queryKeys.media(aid),
    queryKeys.steps(aid),
    queryKeys.printBundles(aid),
  ];
}
