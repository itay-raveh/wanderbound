import { Platform } from "quasar";

export const PHOTO_SHORTCUTS = {
  sendToUnused: "u",
  setAsCover: "c",
} as const;

/** Deferred so the module can be imported in non-browser environments (e.g. Playwright). */
export const KEY_LABELS = {
  get undo() { return Platform.is.mac ? "\u2318Z" : "Ctrl+Z"; },
  get redo() { return Platform.is.mac ? "\u2318\u21e7Z" : "Ctrl+\u21e7Z"; },
};
