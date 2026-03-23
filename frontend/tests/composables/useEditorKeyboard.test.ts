import { withSetup } from "../helpers";
import { useEditorKeyboard } from "@/composables/useEditorKeyboard";
import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { useUndoStack } from "@/composables/useUndoStack";
import { PHOTO_SHORTCUTS } from "@/composables/shortcutKeys";

// useEditorKeyboard attaches a keydown listener in onMounted.
// We mount it via withSetup so the lifecycle hooks fire.

let undoStack: ReturnType<typeof useUndoStack>;
let photoFocus: ReturnType<typeof usePhotoFocus>;

beforeEach(() => {
  // Get singleton APIs to verify calls
  undoStack = useUndoStack();
  undoStack.clear();
  photoFocus = usePhotoFocus();
  photoFocus.blur();
  // Clean up registered steps
  for (const id of [1, 2, 3]) photoFocus.unregister(id);

  // Mount the composable (attaches keydown listener)
  withSetup(() => {
    useEditorKeyboard();
  });
});

function keydown(key: string, opts: Partial<KeyboardEvent> = {}) {
  const event = new KeyboardEvent("keydown", {
    key,
    bubbles: true,
    ...opts,
  });
  document.dispatchEvent(event);
  return event;
}

function keydownOnElement(
  el: HTMLElement,
  key: string,
  opts: Partial<KeyboardEvent> = {},
) {
  const event = new KeyboardEvent("keydown", {
    key,
    bubbles: true,
    ...opts,
  });
  el.dispatchEvent(event);
  return event;
}

// ---------------------------------------------------------------------------
// Escape
// ---------------------------------------------------------------------------

describe("Escape key", () => {
  it("calls photoFocus.blur on Escape", () => {
    const blurSpy = vi.spyOn(photoFocus, "blur");
    keydown("Escape");
    expect(blurSpy).toHaveBeenCalled();
    blurSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// Ctrl+Z / Ctrl+Shift+Z
// ---------------------------------------------------------------------------

describe("undo/redo shortcuts", () => {
  it("calls undo on Ctrl+Z", () => {
    const undoSpy = vi.spyOn(undoStack, "undo");
    keydown("z", { ctrlKey: true });
    expect(undoSpy).toHaveBeenCalled();
    undoSpy.mockRestore();
  });

  it("calls redo on Ctrl+Shift+Z", () => {
    const redoSpy = vi.spyOn(undoStack, "redo");
    keydown("z", { ctrlKey: true, shiftKey: true });
    expect(redoSpy).toHaveBeenCalled();
    redoSpy.mockRestore();
  });

  it("calls undo on Meta+Z (Mac)", () => {
    const undoSpy = vi.spyOn(undoStack, "undo");
    keydown("z", { metaKey: true });
    expect(undoSpy).toHaveBeenCalled();
    undoSpy.mockRestore();
  });

  it("calls redo on Meta+Shift+Z (Mac)", () => {
    const redoSpy = vi.spyOn(undoStack, "redo");
    keydown("z", { metaKey: true, shiftKey: true });
    expect(redoSpy).toHaveBeenCalled();
    redoSpy.mockRestore();
  });

  it("does not call undo when target is an INPUT element", () => {
    const undoSpy = vi.spyOn(undoStack, "undo");
    const input = document.createElement("input");
    document.body.appendChild(input);

    keydownOnElement(input, "z", { ctrlKey: true });
    expect(undoSpy).not.toHaveBeenCalled();

    document.body.removeChild(input);
    undoSpy.mockRestore();
  });

  it("does not call undo when target is a TEXTAREA element", () => {
    const undoSpy = vi.spyOn(undoStack, "undo");
    const textarea = document.createElement("textarea");
    document.body.appendChild(textarea);

    keydownOnElement(textarea, "z", { ctrlKey: true });
    expect(undoSpy).not.toHaveBeenCalled();

    document.body.removeChild(textarea);
    undoSpy.mockRestore();
  });

  it("does not call undo when target is contentEditable", () => {
    const undoSpy = vi.spyOn(undoStack, "undo");
    const div = document.createElement("div");
    div.contentEditable = "true";
    document.body.appendChild(div);

    keydownOnElement(div, "z", { ctrlKey: true });
    expect(undoSpy).not.toHaveBeenCalled();

    document.body.removeChild(div);
    undoSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// Arrow keys
// ---------------------------------------------------------------------------

describe("arrow keys", () => {
  it("calls photoFocus.move('prev') on ArrowLeft in LTR", () => {
    const moveSpy = vi.spyOn(photoFocus, "move");
    document.documentElement.dir = "ltr";

    keydown("ArrowLeft");
    expect(moveSpy).toHaveBeenCalledWith("prev");

    moveSpy.mockRestore();
    document.documentElement.dir = "";
  });

  it("calls photoFocus.move('next') on ArrowRight in LTR", () => {
    const moveSpy = vi.spyOn(photoFocus, "move");
    document.documentElement.dir = "ltr";

    keydown("ArrowRight");
    expect(moveSpy).toHaveBeenCalledWith("next");

    moveSpy.mockRestore();
    document.documentElement.dir = "";
  });

  it("reverses direction in RTL mode", () => {
    const moveSpy = vi.spyOn(photoFocus, "move");
    document.documentElement.dir = "rtl";

    keydown("ArrowLeft");
    expect(moveSpy).toHaveBeenCalledWith("next");

    moveSpy.mockClear();

    keydown("ArrowRight");
    expect(moveSpy).toHaveBeenCalledWith("prev");

    moveSpy.mockRestore();
    document.documentElement.dir = "";
  });

  it("does not fire arrow navigation when target is INPUT", () => {
    const moveSpy = vi.spyOn(photoFocus, "move");
    const input = document.createElement("input");
    document.body.appendChild(input);

    keydownOnElement(input, "ArrowLeft");
    expect(moveSpy).not.toHaveBeenCalled();

    document.body.removeChild(input);
    moveSpy.mockRestore();
  });

  it("does not fire arrow navigation when modifier key is held", () => {
    const moveSpy = vi.spyOn(photoFocus, "move");
    keydown("ArrowLeft", { ctrlKey: true });
    expect(moveSpy).not.toHaveBeenCalled();
    moveSpy.mockRestore();
  });

  it("does not fire arrow navigation when target is VIDEO", () => {
    const moveSpy = vi.spyOn(photoFocus, "move");
    const video = document.createElement("video");
    document.body.appendChild(video);

    keydownOnElement(video, "ArrowLeft");
    expect(moveSpy).not.toHaveBeenCalled();

    document.body.removeChild(video);
    moveSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// Photo shortcut keys (sendToUnused, setAsCover)
// ---------------------------------------------------------------------------

describe("photo shortcut keys", () => {
  it("calls sendToUnused on 'u' key", () => {
    const spy = vi.spyOn(photoFocus, "sendToUnused").mockReturnValue(true);
    keydown(PHOTO_SHORTCUTS.sendToUnused);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it("calls setAsCover on 'c' key", () => {
    const spy = vi.spyOn(photoFocus, "setAsCover").mockReturnValue(true);
    keydown(PHOTO_SHORTCUTS.setAsCover);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it("does not call shortcut keys when target is a text input", () => {
    const spy = vi.spyOn(photoFocus, "sendToUnused");
    const input = document.createElement("input");
    document.body.appendChild(input);

    keydownOnElement(input, PHOTO_SHORTCUTS.sendToUnused);
    expect(spy).not.toHaveBeenCalled();

    document.body.removeChild(input);
    spy.mockRestore();
  });
});
