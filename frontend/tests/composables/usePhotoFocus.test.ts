import { usePhotoFocus } from "@/composables/usePhotoFocus";
import { makeStep } from "../helpers";
import { unusedUpdatePayload, coverUpdatePayload } from "@/composables/useStepLayout";

let pf: ReturnType<typeof usePhotoFocus>;
let scrollSpy: ReturnType<typeof vi.fn>;
let mutateSpy: ReturnType<typeof vi.fn>;

function initWith(steps: ReturnType<typeof makeStep>[]) {
  scrollSpy = vi.fn();
  mutateSpy = vi.fn();
  pf.init({
    steps: () => steps,
    mutate: mutateSpy,
    scrollToStep: scrollSpy,
  });
}

beforeEach(() => {
  pf = usePhotoFocus();
  pf.dispose();
});

// ---------------------------------------------------------------------------
// focus / blur
// ---------------------------------------------------------------------------

describe("focus / blur", () => {
  it("starts with no focus", () => {
    expect(pf.focusedStepId.value).toBeNull();
    expect(pf.focusedPhotoId.value).toBeNull();
  });

  it("sets focused step and photo", () => {
    pf.focus(1, "p2");
    expect(pf.focusedStepId.value).toBe(1);
    expect(pf.focusedPhotoId.value).toBe("p2");
  });

  it("blur clears both", () => {
    pf.focus(1, "p1");
    pf.blur();
    expect(pf.focusedStepId.value).toBeNull();
    expect(pf.focusedPhotoId.value).toBeNull();
  });

  it("dispose clears focus and config", () => {
    initWith([makeStep({ id: 1, pages: [["p1", "p2"]] })]);
    pf.focus(1, "p1");
    pf.dispose();
    expect(pf.focusedStepId.value).toBeNull();
    // After dispose, move should be a no-op
    pf.focus(1, "p1");
    pf.move("next");
    expect(pf.focusedPhotoId.value).toBe("p1");
  });
});

// ---------------------------------------------------------------------------
// pagedPhotos (tested indirectly through move)
// ---------------------------------------------------------------------------

describe("pagedPhotos (via move)", () => {
  it("excludes cover from paged photos", () => {
    initWith([makeStep({ id: 1, cover: "p1", pages: [["p1", "p2", "p3"]] })]);
    pf.focus(1, "p2");
    pf.move("next");
    expect(pf.focusedPhotoId.value).toBe("p3");
  });

  it("includes all photos when there is no cover", () => {
    initWith([makeStep({ id: 1, cover: null, pages: [["p1", "p2"]] })]);
    pf.focus(1, "p1");
    pf.move("next");
    expect(pf.focusedPhotoId.value).toBe("p2");
  });

  it("flattens multi-page arrays", () => {
    initWith([makeStep({ id: 1, pages: [["p1", "p2"], ["p3"]] })]);
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
    initWith([makeStep({ id: 1, pages: [["a", "b", "c"]] })]);
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
    initWith([
      makeStep({ id: 10, pages: [["s1a", "s1b"]] }),
      makeStep({ id: 20, pages: [["s2a", "s2b", "s2c"]] }),
      makeStep({ id: 30, pages: [["s3a"]] }),
    ]);
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
    expect(pf.focusedStepId.value).toBe(10);
    expect(pf.focusedPhotoId.value).toBe("s1a");
  });

  it("stays at last step if no next step exists", () => {
    pf.focus(30, "s3a");
    pf.move("next");
    expect(pf.focusedStepId.value).toBe(30);
    expect(pf.focusedPhotoId.value).toBe("s3a");
  });

  it("skips steps with no paged photos", () => {
    initWith([
      makeStep({ id: 10, pages: [["s1a", "s1b"]] }),
      makeStep({ id: 20, pages: [] }),
      makeStep({ id: 30, pages: [["s3a"]] }),
    ]);
    pf.focus(10, "s1b");
    pf.move("next");
    expect(pf.focusedStepId.value).toBe(30);
    expect(pf.focusedPhotoId.value).toBe("s3a");
  });

  it("skips steps where all photos are the cover", () => {
    initWith([
      makeStep({ id: 10, pages: [["s1a"]] }),
      makeStep({ id: 20, cover: "c2", pages: [["c2"]] }),
      makeStep({ id: 30, pages: [["s3a"]] }),
    ]);
    pf.focus(10, "s1a");
    pf.move("next");
    expect(pf.focusedStepId.value).toBe(30);
    expect(pf.focusedPhotoId.value).toBe("s3a");
  });

  it("calls scrollToStep on cross-step navigation", () => {
    pf.focus(10, "s1b");
    pf.move("next");
    expect(scrollSpy).toHaveBeenCalledWith(20);
  });
});

// ---------------------------------------------------------------------------
// sendToUnused
// ---------------------------------------------------------------------------

describe("sendToUnused", () => {
  it("returns false when no focus", () => {
    initWith([makeStep({ id: 1, pages: [["p1"]] })]);
    expect(pf.sendToUnused()).toBe(false);
  });

  it("calls mutate with unusedUpdatePayload", () => {
    const step = makeStep({ id: 1, pages: [["p1", "p2", "p3"]], unused: ["u1"] });
    initWith([step]);
    pf.focus(1, "p2");

    const result = pf.sendToUnused();

    expect(result).toBe(true);
    expect(mutateSpy).toHaveBeenCalledWith(
      1,
      unusedUpdatePayload(step, ["u1", "p2"]),
    );
  });

  it("advances focus to next photo after sending", () => {
    initWith([makeStep({ id: 1, pages: [["p1", "p2", "p3"]] })]);
    pf.focus(1, "p1");
    pf.sendToUnused();
    expect(pf.focusedPhotoId.value).toBe("p2");
  });

  it("advances focus to previous photo when at end", () => {
    initWith([makeStep({ id: 1, pages: [["p1", "p2", "p3"]] })]);
    pf.focus(1, "p3");
    pf.sendToUnused();
    expect(pf.focusedPhotoId.value).toBe("p2");
  });

  it("clears focus when sending the only photo", () => {
    initWith([makeStep({ id: 1, pages: [["p1"]] })]);
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
    initWith([makeStep({ id: 1, pages: [["p1"]] })]);
    expect(pf.setAsCover()).toBe(false);
  });

  it("calls mutate with coverUpdatePayload", () => {
    const step = makeStep({ id: 1, pages: [["p1", "p2", "p3"]] });
    initWith([step]);
    pf.focus(1, "p2");

    const result = pf.setAsCover();

    expect(result).toBe(true);
    expect(mutateSpy).toHaveBeenCalledWith(
      1,
      coverUpdatePayload(step, "p2"),
    );
  });

  it("advances focus after setting cover", () => {
    initWith([makeStep({ id: 1, pages: [["p1", "p2", "p3"]] })]);
    pf.focus(1, "p1");
    pf.setAsCover();
    expect(pf.focusedPhotoId.value).toBe("p2");
  });
});

// ---------------------------------------------------------------------------
// advanceFocus edge cases
// ---------------------------------------------------------------------------

describe("advanceFocus edge cases", () => {
  it("clears focus when removing from empty list", () => {
    initWith([makeStep({ id: 1, pages: [] })]);
    pf.focus(1, "nonexistent");
    pf.sendToUnused();
    expect(pf.focusedStepId.value).toBeNull();
  });
});
