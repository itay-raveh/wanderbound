import type { AlbumUpdate, StepUpdate } from "@/client";
import type { PhotoFocusSnapshot } from "@/composables/usePhotoFocus";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { ref } from "vue";

type UndoEntry =
  | {
      type: "step";
      sid: number;
      before: StepUpdate;
      after: StepUpdate;
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

let undoEntries: UndoEntry[] = [];
let redoEntries: UndoEntry[] = [];
let replaying = false;

const canUndo = ref(false);
const canRedo = ref(false);

function syncFlags() {
  canUndo.value = undoEntries.length > 0;
  canRedo.value = redoEntries.length > 0;
}

let stepMutator: ((sid: number, update: StepUpdate) => void) | null = null;
let albumMutator: ((update: AlbumUpdate) => void) | null = null;

function replay(
  entry: UndoEntry,
  snapshot: StepUpdate | AlbumUpdate,
  focus?: PhotoFocusSnapshot,
) {
  replaying = true;
  try {
    if (entry.type === "step") {
      stepMutator?.(entry.sid, snapshot as StepUpdate);
      if (focus) usePhotoFocus().restore(focus);
    } else {
      albumMutator?.(snapshot as AlbumUpdate);
    }
  } finally {
    replaying = false;
  }
}

function push(entry: UndoEntry) {
  if (replaying) return;
  if (undoEntries.length >= MAX_STACK) undoEntries.shift();
  undoEntries.push(entry);
  redoEntries = [];
  syncFlags();
}

function undo() {
  const entry = undoEntries.pop();
  if (!entry) return;
  redoEntries.push(entry);
  syncFlags();
  replay(
    entry,
    entry.before,
    entry.type === "step" ? entry.focus?.before : undefined,
  );
}

function redo() {
  const entry = redoEntries.pop();
  if (!entry) return;
  if (undoEntries.length >= MAX_STACK) undoEntries.shift();
  undoEntries.push(entry);
  syncFlags();
  replay(
    entry,
    entry.after,
    entry.type === "step" ? entry.focus?.after : undefined,
  );
}

function clear() {
  undoEntries = [];
  redoEntries = [];
  stepMutator = null;
  albumMutator = null;
  syncFlags();
}

function registerMutators(
  step: (sid: number, update: StepUpdate) => void,
  album: (update: AlbumUpdate) => void,
) {
  stepMutator = step;
  albumMutator = album;
}

const api = { canUndo, canRedo, push, undo, redo, clear, registerMutators };

export function useUndoStack() {
  return api;
}
