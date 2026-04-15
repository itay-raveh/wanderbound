import { useUndoStack } from "@/composables/useUndoStack";

// useUndoStack is a singleton - clear between tests to avoid cross-contamination.
let stack: ReturnType<typeof useUndoStack>;

beforeEach(() => {
  stack = useUndoStack();
  stack.clear();
});

// ---------------------------------------------------------------------------
// Max stack size
// ---------------------------------------------------------------------------

describe("max stack size", () => {
  it("evicts oldest entry when exceeding MAX_STACK on push", () => {
    // MAX_STACK is 50 (internal constant)
    for (let i = 0; i < 55; i++) {
      stack.push({ type: "step", sid: i, before: { name: "old" }, after: { name: "new" } });
    }
    // Should be able to undo 50 times (not 55)
    let undoCount = 0;
    while (stack.canUndo.value) {
      stack.undo();
      undoCount++;
    }
    expect(undoCount).toBe(50);
  });
});
