import { Platform } from "quasar";

export const PHOTO_SHORTCUTS = {
  sendToUnused: "u",
  setAsCover: "c",
} as const;

const mac = Platform.is.mac;

export const KEY_LABELS = {
  undo: mac ? "\u2318Z" : "Ctrl+Z",
  redo: mac ? "\u2318\u21e7Z" : "Ctrl+\u21e7Z",
} as const;
