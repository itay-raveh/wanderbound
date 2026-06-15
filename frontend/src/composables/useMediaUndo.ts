import { undoReplacement } from "@/client";
import { invalidateAlbumKey, queryKeys } from "@/queries/keys";
import { useQueryCache } from "@pinia/colada";
import { Notify } from "quasar";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";

interface UndoState {
  aid: string;
  mediaName: string;
  expiresAt: number;
  pending: boolean;
}

const UNDO_WINDOW_MS = 5 * 60 * 1000;
const undoState = ref<UndoState | null>(null);

let expireTimer: ReturnType<typeof setTimeout> | null = null;
let dismissUndoToast: (() => void) | null = null;

function clearUndoState() {
  undoState.value = null;
  if (expireTimer !== null) {
    clearTimeout(expireTimer);
    expireTimer = null;
  }
  dismissUndoToast?.();
  dismissUndoToast = null;
}

export function useMediaUndo(albumId: () => string) {
  const cache = useQueryCache();
  const { t } = useI18n();

  const currentUndo = computed(() => {
    const state = undoState.value;
    if (!state || state.aid !== albumId()) return null;
    return state;
  });

  function rememberReplacement(mediaName: string) {
    clearUndoState();
    undoState.value = {
      aid: albumId(),
      mediaName,
      expiresAt: Date.now() + UNDO_WINDOW_MS,
      pending: false,
    };
    dismissUndoToast = Notify.create({
      group: false,
      timeout: UNDO_WINDOW_MS,
      type: "positive",
      message: t("externalMedia.undo.toast"),
      actions: [
        {
          label: t("externalMedia.undo.action"),
          color: "white",
          handler: () => {
            void undo();
          },
        },
      ],
    });
    expireTimer = setTimeout(clearUndoState, UNDO_WINDOW_MS);
  }

  async function undo() {
    const state = currentUndo.value;
    if (!state || state.pending) return;
    state.pending = true;
    try {
      await undoReplacement({
        path: { aid: state.aid, media_name: state.mediaName },
      });
      await Promise.all(
        mediaUndoInvalidationKeys(state.aid).map((key) =>
          cache.invalidateQueries(invalidateAlbumKey(key)),
        ),
      );
      Notify.create({
        type: "positive",
        message: t("externalMedia.undo.done"),
      });
      clearUndoState();
    } catch {
      state.pending = false;
      Notify.create({
        type: "negative",
        message: t("externalMedia.undo.failed"),
      });
    }
  }

  return {
    currentUndo,
    rememberReplacement,
    undo,
    clearUndoState,
  };
}

export function mediaUndoInvalidationKeys(aid: string) {
  return [
    queryKeys.album(aid),
    queryKeys.media(aid),
    queryKeys.steps(aid),
    queryKeys.printBundles(aid),
  ];
}
