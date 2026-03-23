import { usePhotoFocus, type StepFocusContext } from "@/composables/usePhotoFocus";
import type { Step } from "@/client";
import { ref, type Ref } from "vue";
import { makeStep } from "../helpers";

// usePhotoFocus is a singleton — get the API once and reset between tests.
let pf: ReturnType<typeof usePhotoFocus>;

function makeContext(step: Step, onCover = vi.fn(), onUnused = vi.fn()): StepFocusContext {
  return {
    step: ref(step) as Ref<Step>,
    onCoverUpdate: onCover,
    onUnusedUpdate: onUnused,
  };
}

beforeEach(() => {
  pf = usePhotoFocus();
  pf.blur();
  // Unregister all known step IDs by blurring — but we also need to clear registry.
  // Since there's no public "clearAll", we unregister specific IDs used in tests.
  for (const id of [1, 2, 3, 10, 20, 30]) {
    pf.unregister(id);
  }
  pf.setStepOrder(() => []);
});

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

describe("registry management", () => {
  it("starts with no focus", () => {
    expect(pf.focusedStepId.value).toBeNull();
    expect(pf.focusedPhotoId.value).toBeNull();
  });

  it("register and unregister a step context", () => {
    const step = makeStep({ id: 1, pages: [["p1"]] });
    const ctx = makeContext(step);
    pf.register(1, ctx);

    pf.focus(1, "p1");
    expect(pf.focusedStepId.value).toBe(1);
    expect(pf.focusedPhotoId.value).toBe("p1");

    pf.unregister(1);
    // Unregistering the focused step clears focus
    expect(pf.focusedStepId.value).toBeNull();
    expect(pf.focusedPhotoId.value).toBeNull();
  });

  it("unregistering a non-focused step does not clear focus", () => {
    const step1 = makeStep({ id: 1, pages: [["p1"]] });
    const step2 = makeStep({ id: 2, pages: [["p2"]] });
    pf.register(1, makeContext(step1));
    pf.register(2, makeContext(step2));

    pf.focus(1, "p1");
    pf.unregister(2);

    expect(pf.focusedStepId.value).toBe(1);
    expect(pf.focusedPhotoId.value).toBe("p1");
  });
});

// ---------------------------------------------------------------------------
// focus / blur
// ---------------------------------------------------------------------------

describe("focus / blur", () => {
  it("sets focused step and photo", () => {
    pf.register(1, makeContext(makeStep({ id: 1, pages: [["p1", "p2"]] })));
    pf.focus(1, "p2");
    expect(pf.focusedStepId.value).toBe(1);
    expect(pf.focusedPhotoId.value).toBe("p2");
  });

  it("blur clears both", () => {
    pf.register(1, makeContext(makeStep({ id: 1, pages: [["p1"]] })));
    pf.focus(1, "p1");
    pf.blur();
    expect(pf.focusedStepId.value).toBeNull();
    expect(pf.focusedPhotoId.value).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// pagedPhotos (tested indirectly through move)
// ---------------------------------------------------------------------------

describe("pagedPhotos (via move)", () => {
  it("excludes cover from paged photos", () => {
    // Step with cover "p1" and pages [["p1", "p2", "p3"]]
    // pagedPhotos should return ["p2", "p3"]
    const step = makeStep({ id: 1, cover: "p1", pages: [["p1", "p2", "p3"]] });
    pf.register(1, makeContext(step));
    pf.setStepOrder(() => [1]);

    // Focus on p2, move next should go to p3 (not p1)
    pf.focus(1, "p2");
    pf.move("next");
    expect(pf.focusedPhotoId.value).toBe("p3");
  });

  it("includes all photos when there is no cover", () => {
    const step = makeStep({ id: 1, cover: null, pages: [["p1", "p2"]] });
    pf.register(1, makeContext(step));
    pf.setStepOrder(() => [1]);

    pf.focus(1, "p1");
    pf.move("next");
    expect(pf.focusedPhotoId.value).toBe("p2");
  });

  it("flattens multi-page arrays", () => {
    const step = makeStep({ id: 1, pages: [["p1", "p2"], ["p3"]] });
    pf.register(1, makeContext(step));
    pf.setStepOrder(() => [1]);

    pf.focus(1, "p1");
    pf.move("next");
    expect(pf.focusedPhotoId.value).toBe("p2");

    pf.move("next");
    expect(pf.focusedPhotoId.value).toBe("p3");
  });
});

// ---------------------------------------------------------------------------
// move within a step
// ---------------------------------------------------------------------------

describe("move within step", () => {
  beforeEach(() => {
    const step = makeStep({ id: 1, pages: [["a", "b", "c"]] });
    pf.register(1, makeContext(step));
    pf.setStepOrder(() => [1]);
  });

  it("move next advances to next photo", () => {
    pf.focus(1, "a");
    pf.move("next");
    expect(pf.focusedPhotoId.value).toBe("b");
  });

  it("move prev goes to previous photo", () => {
    pf.focus(1, "c");
    pf.move("prev");
    expect(pf.focusedPhotoId.value).toBe("b");
  });

  it("move does nothing without focus", () => {
    pf.move("next");
    expect(pf.focusedPhotoId.value).toBeNull();
  });

  it("focuses first photo on 'next' when current photo not found", () => {
    pf.focus(1, "nonexistent");
    pf.move("next");
    expect(pf.focusedPhotoId.value).toBe("a");
  });

  it("focuses last photo on 'prev' when current photo not found", () => {
    pf.focus(1, "nonexistent");
    pf.move("prev");
    expect(pf.focusedPhotoId.value).toBe("c");
  });
});

// ---------------------------------------------------------------------------
// move across steps
// ---------------------------------------------------------------------------

describe("move across steps", () => {
  beforeEach(() => {
    const step1 = makeStep({ id: 10, pages: [["s1a", "s1b"]] });
    const step2 = makeStep({ id: 20, pages: [["s2a", "s2b", "s2c"]] });
    const step3 = makeStep({ id: 30, pages: [["s3a"]] });

    pf.register(10, makeContext(step1));
    pf.register(20, makeContext(step2));
    pf.register(30, makeContext(step3));
    pf.setStepOrder(() => [10, 20, 30]);
  });

  it("moves to first photo of next step at end of current step", () => {
    pf.focus(10, "s1b");
    pf.move("next");
    expect(pf.focusedStepId.value).toBe(20);
    expect(pf.focusedPhotoId.value).toBe("s2a");
  });

  it("moves to last photo of previous step at start of current step", () => {
    pf.focus(20, "s2a");
    pf.move("prev");
    expect(pf.focusedStepId.value).toBe(10);
    expect(pf.focusedPhotoId.value).toBe("s1b");
  });

  it("stays at first step if no previous step exists", () => {
    pf.focus(10, "s1a");
    pf.move("prev");
    // Should not change because there's no step before 10
    expect(pf.focusedStepId.value).toBe(10);
    expect(pf.focusedPhotoId.value).toBe("s1a");
  });

  it("stays at last step if no next step exists", () => {
    pf.focus(30, "s3a");
    pf.move("next");
    // Should not change because there's no step after 30
    expect(pf.focusedStepId.value).toBe(30);
    expect(pf.focusedPhotoId.value).toBe("s3a");
  });

  it("skips steps with no paged photos", () => {
    // Register a step in the middle with no photos
    const emptyStep = makeStep({ id: 20, pages: [] });
    pf.register(20, makeContext(emptyStep)); // override step 20 with empty pages

    pf.focus(10, "s1b");
    pf.move("next");
    // Should skip step 20 and go to step 30
    expect(pf.focusedStepId.value).toBe(30);
    expect(pf.focusedPhotoId.value).toBe("s3a");
  });
});

// ---------------------------------------------------------------------------
// sendToUnused
// ---------------------------------------------------------------------------

describe("sendToUnused", () => {
  it("returns false when no focus", () => {
    expect(pf.sendToUnused()).toBe(false);
  });

  it("calls onUnusedUpdate with photo added to unused list", () => {
    const onUnused = vi.fn();
    const step = makeStep({ id: 1, pages: [["p1", "p2", "p3"]], unused: ["u1"] });
    pf.register(1, makeContext(step, vi.fn(), onUnused));
    pf.setStepOrder(() => [1]);

    pf.focus(1, "p2");
    const result = pf.sendToUnused();

    expect(result).toBe(true);
    expect(onUnused).toHaveBeenCalledWith(["u1", "p2"]);
  });

  it("advances focus to next photo after sending", () => {
    const step = makeStep({ id: 1, pages: [["p1", "p2", "p3"]] });
    pf.register(1, makeContext(step));
    pf.setStepOrder(() => [1]);

    pf.focus(1, "p1");
    pf.sendToUnused();
    // p1 was at index 0, next photo is at index 1 = p2
    expect(pf.focusedPhotoId.value).toBe("p2");
  });

  it("advances focus to previous photo when at end", () => {
    const step = makeStep({ id: 1, pages: [["p1", "p2", "p3"]] });
    pf.register(1, makeContext(step));
    pf.setStepOrder(() => [1]);

    pf.focus(1, "p3");
    pf.sendToUnused();
    // p3 was at last index, so advance goes to previous = p2
    expect(pf.focusedPhotoId.value).toBe("p2");
  });

  it("clears focus when sending the only photo", () => {
    const step = makeStep({ id: 1, pages: [["p1"]] });
    pf.register(1, makeContext(step));
    pf.setStepOrder(() => [1]);

    pf.focus(1, "p1");
    pf.sendToUnused();
    expect(pf.focusedStepId.value).toBeNull();
    expect(pf.focusedPhotoId.value).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// setAsCover
// ---------------------------------------------------------------------------

describe("setAsCover", () => {
  it("returns false when no focus", () => {
    expect(pf.setAsCover()).toBe(false);
  });

  it("calls onCoverUpdate with the focused photo", () => {
    const onCover = vi.fn();
    const step = makeStep({ id: 1, pages: [["p1", "p2", "p3"]] });
    pf.register(1, makeContext(step, onCover));
    pf.setStepOrder(() => [1]);

    pf.focus(1, "p2");
    const result = pf.setAsCover();

    expect(result).toBe(true);
    expect(onCover).toHaveBeenCalledWith("p2");
  });

  it("advances focus after setting cover", () => {
    const step = makeStep({ id: 1, pages: [["p1", "p2", "p3"]] });
    pf.register(1, makeContext(step));
    pf.setStepOrder(() => [1]);

    pf.focus(1, "p1");
    pf.setAsCover();
    // p1 was at index 0, next photo = p2
    expect(pf.focusedPhotoId.value).toBe("p2");
  });
});

// ---------------------------------------------------------------------------
// advanceFocus edge cases (tested indirectly)
// ---------------------------------------------------------------------------

describe("advanceFocus edge cases", () => {
  it("clears focus when removing from empty list", () => {
    const step = makeStep({ id: 1, pages: [] });
    pf.register(1, makeContext(step));
    pf.setStepOrder(() => [1]);

    pf.focus(1, "nonexistent");
    pf.sendToUnused();
    // advanceFocus called with removedIdx = -1 => clears focus
    expect(pf.focusedStepId.value).toBeNull();
  });
});
