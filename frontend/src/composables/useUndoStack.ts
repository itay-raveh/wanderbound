import type { AlbumUpdate } from "@/client";
import type { PhotoFocusSnapshot } from "@/composables/usePhotoFocus";
import type { StepMutationUpdate } from "@/queries/useStepMutation";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { ref } from "vue";

type UndoEntry =
  | {
      type: "step";
      sid: number;
      before: StepMutationUpdate;
      after: StepMutationUpdate;
      focus?: { before: PhotoFocusSnapshot; after: PhotoFocusSnapshot };
    }
  | { type: "album"; before: AlbumUpdate; after: AlbumUpdate };

export function pickSnapshot<T extends object>(
  source: T,
  keys: (keyof T)[],
): Partial<T> {
  const snap: Partial<T> = {};
  for (const k of keys) snap[k] = source[k];
  return snap;
}

const MAX_STACK = 50;

export function createUndoStack(maxEntries: number) {
  let undoEntries: UndoEntry[] = [];
  let redoEntries: UndoEntry[] = [];
  let replaying = false;
  let replayRollback: (() => void) | undefined;
  let pending = 0;
  let generation = 0;

  const canUndo = ref(false);
  const canRedo = ref(false);

  function syncFlags() {
    canUndo.value = pending === 0 && undoEntries.length > 0;
    canRedo.value = pending === 0 && redoEntries.length > 0;
  }

  let stepMutator: ((sid: number, update: StepMutationUpdate) => void) | null =
    null;
  let albumMutator: ((update: AlbumUpdate) => void) | null = null;

  function replay(
    entry: UndoEntry,
    snapshot: StepMutationUpdate | AlbumUpdate,
    focus?: PhotoFocusSnapshot,
    rollback?: () => void,
  ) {
    replaying = true;
    replayRollback = rollback;
    try {
      if (entry.type === "step") {
        stepMutator?.(entry.sid, snapshot as StepMutationUpdate);
        if (focus) usePhotoFocus().restore(focus);
      } else {
        albumMutator?.(snapshot as AlbumUpdate);
      }
    } finally {
      replaying = false;
      replayRollback = undefined;
    }
  }

  function push(entry: UndoEntry) {
    if (replaying) return;
    if (undoEntries.length >= maxEntries) undoEntries.shift();
    undoEntries.push(entry);
    redoEntries = [];
    syncFlags();
    return entry;
  }

  function capturePush() {
    const originalGeneration = generation;
    const wasReplaying = replaying;
    return (entry: UndoEntry) => {
      if (!wasReplaying && generation === originalGeneration)
        return push(entry);
    };
  }

  function captureRollback() {
    const originalGeneration = generation;
    const rollback = replayRollback;
    return () => {
      if (generation === originalGeneration) rollback?.();
    };
  }

  function discard(entry: UndoEntry | undefined) {
    if (!entry) return;
    undoEntries = undoEntries.filter((item) => item !== entry);
    redoEntries = redoEntries.filter((item) => item !== entry);
    syncFlags();
  }

  function suspend() {
    pending++;
    syncFlags();
    return () => {
      pending--;
      syncFlags();
    };
  }

  function undo() {
    if (pending) return;
    const entry = undoEntries.pop();
    if (!entry) return;
    redoEntries.push(entry);
    syncFlags();
    replay(
      entry,
      entry.before,
      entry.type === "step" ? entry.focus?.before : undefined,
      () => {
        redoEntries = redoEntries.filter((item) => item !== entry);
        undoEntries.push(entry);
        syncFlags();
      },
    );
  }

  function redo() {
    if (pending) return;
    const entry = redoEntries.pop();
    if (!entry) return;
    if (undoEntries.length >= maxEntries) undoEntries.shift();
    undoEntries.push(entry);
    syncFlags();
    replay(
      entry,
      entry.after,
      entry.type === "step" ? entry.focus?.after : undefined,
      () => {
        undoEntries = undoEntries.filter((item) => item !== entry);
        redoEntries.push(entry);
        syncFlags();
      },
    );
  }

  function clear() {
    generation++;
    undoEntries = [];
    redoEntries = [];
    stepMutator = null;
    albumMutator = null;
    syncFlags();
  }

  function registerMutators(
    step: (sid: number, update: StepMutationUpdate) => void,
    album: (update: AlbumUpdate) => void,
  ) {
    stepMutator = step;
    albumMutator = album;
  }

  return {
    canUndo,
    canRedo,
    push,
    capturePush,
    captureRollback,
    discard,
    suspend,
    undo,
    redo,
    clear,
    registerMutators,
  };
}

const undoStack = createUndoStack(MAX_STACK);

export function useUndoStack() {
  return undoStack;
}
