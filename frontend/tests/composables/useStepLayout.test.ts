/**
 * Tests for useStepLayout's pure logic functions.
 *
 * useStepLayout itself is tightly coupled (useDraggable, inject, usePrintMode),
 * so we test the logic by mounting it with withSetup + providing dependencies.
 * The key functions tested: withoutPhotos (via onCoverUpdate/onPageUpdate),
 * and the various list-management operations.
 */

import { createApp, defineComponent, h, ref, type Ref } from "vue";
import type { Step, StepUpdate } from "@/client";
import { provideStepMutate, useStepLayout } from "@/composables/useStepLayout";
import { makeStep } from "../helpers";

// Mock vue-draggable-plus to avoid DOM requirements
vi.mock("vue-draggable-plus", () => ({
  useDraggable: vi.fn(),
}));

interface LayoutResult {
  saveField: (patch: Partial<StepUpdate>) => void;
  onPageUpdate: (idx: number, page: string[]) => void;
  onCoverUpdate: (cover: string) => void;
  printMode: boolean;
}

/**
 * Mount useStepLayout with a provided step and mutate function.
 * Returns the composable's API and the mutate spy.
 */
function mountStepLayout(step: Step) {
  const stepRef = ref(step);
  const mutateSpy = vi.fn<(payload: { sid: number; update: StepUpdate }) => void>();
  let result!: LayoutResult;

  const Child = defineComponent({
    setup() {
      const dropZoneRef = ref(null);
      const coverDropRef = ref(null);
      result = useStepLayout(stepRef as Ref<Step>, { dropZoneRef, coverDropRef });
      return () => null;
    },
  });

  const Parent = defineComponent({
    setup() {
      provideStepMutate(mutateSpy);
      return () => h(Child);
    },
  });

  const app = createApp(Parent);
  app.mount(document.createElement("div"));

  onTestFinished(() => {
    app.unmount();
  });

  return { result, mutateSpy, stepRef };
}

// ---------------------------------------------------------------------------
// onCoverUpdate
// ---------------------------------------------------------------------------

describe("onCoverUpdate", () => {
  it("sets cover and removes photo from pages", () => {
    const step = makeStep({
      id: 1,
      cover: null,
      pages: [["p1", "p2"], ["p3"]],
      unused: [],
    });
    const { result, mutateSpy } = mountStepLayout(step);

    result.onCoverUpdate("p2");

    expect(mutateSpy).toHaveBeenCalledOnce();
    const payload = mutateSpy.mock.calls[0][0];
    expect(payload.sid).toBe(1);
    expect(payload.update.cover).toBe("p2");
    // p2 should be removed from pages
    expect(payload.update.pages).toEqual([["p1"], ["p3"]]);
    // No old cover to add to unused
    expect(payload.update.unused).toEqual([]);

  });

  it("moves old cover to unused when replacing", () => {
    const step = makeStep({
      id: 1,
      cover: "old_cover",
      pages: [["p1", "new_cover"]],
      unused: ["u1"],
    });
    const { result, mutateSpy } = mountStepLayout(step);

    result.onCoverUpdate("new_cover");

    const payload = mutateSpy.mock.calls[0][0];
    expect(payload.update.cover).toBe("new_cover");
    expect(payload.update.pages).toEqual([["p1"]]);
    // Old cover should be added to unused list
    expect(payload.update.unused).toEqual(["u1", "old_cover"]);

  });

  it("removes cover photo from unused if it was there", () => {
    const step = makeStep({
      id: 1,
      cover: null,
      pages: [],
      unused: ["u1", "new_cover", "u2"],
    });
    const { result, mutateSpy } = mountStepLayout(step);

    result.onCoverUpdate("new_cover");

    const payload = mutateSpy.mock.calls[0][0];
    expect(payload.update.cover).toBe("new_cover");
    expect(payload.update.unused).toEqual(["u1", "u2"]);

  });
});

// ---------------------------------------------------------------------------
// onPageUpdate
// ---------------------------------------------------------------------------

describe("onPageUpdate", () => {
  it("handles cross-list moves: strips added photos from other pages", () => {
    const step = makeStep({
      id: 1,
      pages: [["a", "b"], ["c", "d"]],
      unused: [],
    });
    const { result, mutateSpy } = mountStepLayout(step);

    // "c" dragged from page 1 to page 0
    result.onPageUpdate(0, ["a", "b", "c"]);

    const payload = mutateSpy.mock.calls[0][0];
    expect(payload.update.pages).toEqual([["a", "b", "c"], ["d"]]);
    expect(payload.update.unused).toEqual([]);

  });

  it("strips photos from unused when moved to a page", () => {
    const step = makeStep({
      id: 1,
      pages: [["a"]],
      unused: ["u1", "u2"],
    });
    const { result, mutateSpy } = mountStepLayout(step);

    // "u1" dragged from unused to page 0
    result.onPageUpdate(0, ["a", "u1"]);

    const payload = mutateSpy.mock.calls[0][0];
    expect(payload.update.pages).toEqual([["a", "u1"]]);
    expect(payload.update.unused).toEqual(["u2"]);

  });

  it("filters out empty pages after cross-list move", () => {
    const step = makeStep({
      id: 1,
      pages: [["a"], ["b"]],
      unused: [],
    });
    const { result, mutateSpy } = mountStepLayout(step);

    // Move "b" from page 1 to page 0
    result.onPageUpdate(0, ["a", "b"]);

    const payload = mutateSpy.mock.calls[0][0];
    // Page 1 becomes empty after removing "b", should be filtered out
    expect(payload.update.pages).toEqual([["a", "b"]]);

  });
});
