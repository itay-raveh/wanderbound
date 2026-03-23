import type { UndoEntry } from "@/composables/useUndoStack";
import { useUndoStack, pickSnapshot } from "@/composables/useUndoStack";
import type { StepUpdate, AlbumUpdate } from "@/client";

// useUndoStack is a singleton — clear between tests to avoid cross-contamination.
let stack: ReturnType<typeof useUndoStack>;

beforeEach(() => {
  stack = useUndoStack();
  stack.clear();
});

function makeStepEntry(
  sid: number,
  before: StepUpdate = { name: "old" },
  after: StepUpdate = { name: "new" },
): UndoEntry {
  return { type: "step", sid, before, after };
}

function makeAlbumEntry(
  before: AlbumUpdate = { title: "old" },
  after: AlbumUpdate = { title: "new" },
): UndoEntry {
  return { type: "album", before, after };
}

// ---------------------------------------------------------------------------
// pickSnapshot
// ---------------------------------------------------------------------------

describe("pickSnapshot", () => {
  it("picks specified keys from an object", () => {
    const src = { a: 1, b: "hello", c: true };
    expect(pickSnapshot(src, ["a", "c"])).toEqual({ a: 1, c: true });
  });

  it("returns empty object when no keys specified", () => {
    expect(pickSnapshot({ x: 1 }, [])).toEqual({});
  });

  it("includes undefined values for missing keys", () => {
    const src = { a: 1 } as { a: number; b?: string };
    const snap = pickSnapshot(src, ["a", "b"]);
    expect(snap).toEqual({ a: 1, b: undefined });
    expect("b" in snap).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// canUndo / canRedo reactivity
// ---------------------------------------------------------------------------

describe("canUndo / canRedo", () => {
  it("starts with both false", () => {
    expect(stack.canUndo.value).toBe(false);
    expect(stack.canRedo.value).toBe(false);
  });

  it("canUndo becomes true after push", () => {
    stack.push(makeStepEntry(1));
    expect(stack.canUndo.value).toBe(true);
    expect(stack.canRedo.value).toBe(false);
  });

  it("canRedo becomes true after undo", () => {
    stack.push(makeStepEntry(1));
    stack.undo();
    expect(stack.canUndo.value).toBe(false);
    expect(stack.canRedo.value).toBe(true);
  });

  it("both become false after clear", () => {
    stack.push(makeStepEntry(1));
    stack.push(makeStepEntry(2));
    stack.clear();
    expect(stack.canUndo.value).toBe(false);
    expect(stack.canRedo.value).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// push / undo / redo
// ---------------------------------------------------------------------------

describe("push", () => {
  it("adds entry to the undo stack", () => {
    stack.push(makeStepEntry(1));
    expect(stack.canUndo.value).toBe(true);
  });

  it("clears redo stack on new push", () => {
    stack.push(makeStepEntry(1));
    stack.undo();
    expect(stack.canRedo.value).toBe(true);

    stack.push(makeStepEntry(2));
    expect(stack.canRedo.value).toBe(false);
  });
});

describe("undo", () => {
  it("does nothing when stack is empty", () => {
    stack.undo(); // should not throw
    expect(stack.canUndo.value).toBe(false);
    expect(stack.canRedo.value).toBe(false);
  });

  it("calls step mutator with 'before' snapshot", () => {
    const stepMutator = vi.fn();
    const albumMutator = vi.fn();
    stack.registerMutators(stepMutator, albumMutator);

    const before: StepUpdate = { name: "original" };
    const after: StepUpdate = { name: "changed" };
    stack.push({ type: "step", sid: 42, before, after });
    stack.undo();

    expect(stepMutator).toHaveBeenCalledWith(42, before);
    expect(albumMutator).not.toHaveBeenCalled();
  });

  it("calls album mutator with 'before' snapshot", () => {
    const stepMutator = vi.fn();
    const albumMutator = vi.fn();
    stack.registerMutators(stepMutator, albumMutator);

    const before: AlbumUpdate = { title: "original" };
    const after: AlbumUpdate = { title: "changed" };
    stack.push({ type: "album", before, after });
    stack.undo();

    expect(albumMutator).toHaveBeenCalledWith(before);
    expect(stepMutator).not.toHaveBeenCalled();
  });

  it("moves entry to redo stack", () => {
    stack.push(makeStepEntry(1));
    stack.undo();
    expect(stack.canUndo.value).toBe(false);
    expect(stack.canRedo.value).toBe(true);
  });
});

describe("redo", () => {
  it("does nothing when redo stack is empty", () => {
    stack.redo(); // should not throw
    expect(stack.canRedo.value).toBe(false);
  });

  it("calls step mutator with 'after' snapshot", () => {
    const stepMutator = vi.fn();
    const albumMutator = vi.fn();
    stack.registerMutators(stepMutator, albumMutator);

    const before: StepUpdate = { name: "original" };
    const after: StepUpdate = { name: "changed" };
    stack.push({ type: "step", sid: 42, before, after });
    stack.undo();
    stepMutator.mockClear();

    stack.redo();
    expect(stepMutator).toHaveBeenCalledWith(42, after);
  });

  it("moves entry back to undo stack", () => {
    stack.push(makeStepEntry(1));
    stack.undo();
    stack.redo();
    expect(stack.canUndo.value).toBe(true);
    expect(stack.canRedo.value).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Replay flag (push is ignored during undo/redo)
// ---------------------------------------------------------------------------

describe("replay suppression", () => {
  it("ignores push calls made during undo replay", () => {
    // Register a mutator that tries to push during replay
    const stepMutator = vi.fn(() => {
      stack.push(makeStepEntry(99));
    });
    stack.registerMutators(stepMutator, vi.fn());

    stack.push(makeStepEntry(1));
    stack.push(makeStepEntry(2));
    stack.undo();

    // Only 1 entry should remain (entry 1), not entry 1 + the push from mutator
    expect(stack.canUndo.value).toBe(true);
    stack.undo();
    expect(stack.canUndo.value).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Max stack size
// ---------------------------------------------------------------------------

describe("max stack size", () => {
  it("evicts oldest entry when exceeding MAX_STACK on push", () => {
    // MAX_STACK is 50 (internal constant)
    for (let i = 0; i < 55; i++) {
      stack.push(makeStepEntry(i));
    }
    // Should be able to undo 50 times (not 55)
    let undoCount = 0;
    while (stack.canUndo.value) {
      stack.undo();
      undoCount++;
    }
    expect(undoCount).toBe(50);
  });

  it("evicts oldest entry when exceeding MAX_STACK on redo", () => {
    // Fill undo stack to max
    for (let i = 0; i < 50; i++) {
      stack.push(makeStepEntry(i));
    }
    // Undo all
    for (let i = 0; i < 50; i++) {
      stack.undo();
    }
    // Redo all — each redo pushes back to undo, respecting MAX_STACK
    for (let i = 0; i < 50; i++) {
      stack.redo();
    }
    expect(stack.canUndo.value).toBe(true);
    expect(stack.canRedo.value).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Multiple undo/redo cycles
// ---------------------------------------------------------------------------

describe("undo/redo cycles", () => {
  it("supports multiple undo then redo in order", () => {
    const stepMutator = vi.fn();
    stack.registerMutators(stepMutator, vi.fn());

    stack.push(makeStepEntry(1, { name: "a" }, { name: "b" }));
    stack.push(makeStepEntry(2, { name: "c" }, { name: "d" }));
    stack.push(makeStepEntry(3, { name: "e" }, { name: "f" }));

    // Undo 3 -> replays before of entry 3
    stack.undo();
    expect(stepMutator).toHaveBeenLastCalledWith(3, { name: "e" });

    // Undo 2 -> replays before of entry 2
    stack.undo();
    expect(stepMutator).toHaveBeenLastCalledWith(2, { name: "c" });

    // Redo -> replays after of entry 2
    stack.redo();
    expect(stepMutator).toHaveBeenLastCalledWith(2, { name: "d" });

    // Redo -> replays after of entry 3
    stack.redo();
    expect(stepMutator).toHaveBeenLastCalledWith(3, { name: "f" });
  });
});

// ---------------------------------------------------------------------------
// Album entries
// ---------------------------------------------------------------------------

describe("album entries", () => {
  it("handles album undo/redo through album mutator", () => {
    const albumMutator = vi.fn();
    stack.registerMutators(vi.fn(), albumMutator);

    stack.push(makeAlbumEntry({ title: "old" }, { title: "new" }));
    stack.undo();
    expect(albumMutator).toHaveBeenCalledWith({ title: "old" });

    stack.redo();
    expect(albumMutator).toHaveBeenCalledWith({ title: "new" });
  });
});
