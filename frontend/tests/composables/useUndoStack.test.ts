import { createUndoStack } from "@/composables/useUndoStack";

it("evicts the oldest undo entry when capacity is exceeded", () => {
  const stack = createUndoStack(2);
  const restored: number[] = [];
  stack.registerMutators((sid) => restored.push(sid), vi.fn());

  for (const sid of [1, 2, 3]) {
    stack.push({
      type: "step",
      sid,
      before: { name: "old" },
      after: { name: "new" },
    });
  }
  stack.undo();
  stack.undo();
  stack.undo();

  expect(restored).toEqual([3, 2]);
});

it("keeps asynchronous replay out of history and recovers a failed undo or redo", () => {
  const stack = createUndoStack(50);
  let complete = () => {};
  let fail = () => {};
  let push = stack.capturePush();
  stack.registerMutators(vi.fn(), () => {
    push = stack.capturePush();
    fail = stack.captureRollback();
    complete = stack.suspend();
  });
  const entry = {
    type: "album" as const,
    before: { page_width_mm: 297 },
    after: { page_width_mm: 300 },
  };
  stack.push(entry);
  stack.undo();
  expect(stack.canRedo.value).toBe(false);
  push(entry);
  fail();
  complete();
  expect(stack.canUndo.value).toBe(true);
  expect(stack.canRedo.value).toBe(false);
  stack.undo();
  complete();
  expect(stack.canRedo.value).toBe(true);
  stack.redo();
  fail();
  complete();
  expect(stack.canRedo.value).toBe(true);
  expect(stack.canUndo.value).toBe(false);
  stack.clear();
  push(entry);
  fail();
  expect(stack.canUndo.value).toBe(false);
});
