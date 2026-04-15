import { PHOTO_SHORTCUTS } from "./shortcutKeys";
import { useUndoStack } from "./useUndoStack";
import { usePhotoFocus } from "./usePhotoFocus";
import { onMounted, onUnmounted } from "vue";

export function useEditorKeyboard() {
  const undoStack = useUndoStack();
  const photoFocus = usePhotoFocus();

  function isTextInput(e: KeyboardEvent): boolean {
    const el = e.target as HTMLElement;
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      photoFocus.blur();
      return;
    }

    const mod = e.metaKey || e.ctrlKey;
    const key = e.key.toLowerCase();

    if (mod && key === "z") {
      if (isTextInput(e)) return;
      e.preventDefault();
      if (e.shiftKey) undoStack.redo();
      else undoStack.undo();
      return;
    }

    if (isTextInput(e)) return;
    // Video has focus (playing or paused): let native controls handle keys
    const el = e.target as HTMLElement;
    if (el.tagName === "VIDEO") return;
    if (mod) return;

    const rtl = document.documentElement.dir === "rtl";

    switch (key) {
      case "arrowleft":
        e.preventDefault();
        photoFocus.move(rtl ? "next" : "prev");
        break;
      case "arrowright":
        e.preventDefault();
        photoFocus.move(rtl ? "prev" : "next");
        break;
      case PHOTO_SHORTCUTS.sendToUnused:
        if (photoFocus.sendToUnused()) e.preventDefault();
        break;
      case PHOTO_SHORTCUTS.setAsCover:
        if (photoFocus.setAsCover()) e.preventDefault();
        break;
    }
  }

  onMounted(() => document.addEventListener("keydown", onKeydown));
  onUnmounted(() => document.removeEventListener("keydown", onKeydown));
}
