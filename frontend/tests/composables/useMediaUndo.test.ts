import { mediaUndoInvalidationKeys } from "@/composables/useMediaUndo";
import { queryKeys } from "@/queries/keys";

describe("mediaUndoInvalidationKeys", () => {
  it("invalidates print bundle after replacement undo", () => {
    expect(mediaUndoInvalidationKeys("album-1")).toEqual([
      queryKeys.album("album-1"),
      queryKeys.media("album-1"),
      queryKeys.steps("album-1"),
      queryKeys.printBundle("album-1"),
    ]);
  });
});
