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
