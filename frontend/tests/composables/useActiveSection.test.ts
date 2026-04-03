import { useActiveSection, pickBestItem } from "@/composables/useActiveSection";
import type { VirtualItem } from "@tanstack/vue-virtual";
import { activeSectionId, HEADER_KEYS, type Section } from "@/components/album/albumSections";
import { makeStep } from "../helpers";
import type { DateRange } from "@/client";

vi.mock("@/composables/useTextLayout", () => ({
  layoutDescription: (text: string) => {
    if (!text || text.length < 100) return { pages: [] };
    return { pages: [[], []] };
  },
}));

describe("useActiveSection", () => {
  afterEach(() => {
    const { resetActiveSection } = useActiveSection();
    resetActiveSection();
  });

  describe("setActive", () => {
    it("sets activeStepId for a number and clears activeSectionKey", () => {
      const { setActive, activeStepId, activeSectionKey } = useActiveSection();
      setActive("cover-front");
      setActive(42);
      expect(activeStepId.value).toBe(42);
      expect(activeSectionKey.value).toBeNull();
    });

    it("sets activeSectionKey for a string and clears activeStepId", () => {
      const { setActive, activeStepId, activeSectionKey } = useActiveSection();
      setActive(42);
      setActive("overview");
      expect(activeSectionKey.value).toBe("overview");
      expect(activeStepId.value).toBeNull();
    });

    it("clears both refs for null", () => {
      const { setActive, activeStepId, activeSectionKey } = useActiveSection();
      setActive(42);
      setActive(null);
      expect(activeStepId.value).toBeNull();
      expect(activeSectionKey.value).toBeNull();
    });
  });

  describe("resetActiveSection", () => {
    it("clears refs and scroll override", () => {
      const overrideScrollTo = vi.fn();
      const { setActive, setScrollOverride, scrollTo, resetActiveSection, activeStepId } = useActiveSection();

      setActive(10);
      setScrollOverride({ scrollTo: overrideScrollTo, scrollToSection: () => false });

      resetActiveSection();

      expect(activeStepId.value).toBeNull();
      scrollTo(10);
      expect(overrideScrollTo).not.toHaveBeenCalled();
    });
  });

  describe("setScrollOverride", () => {
    it("scrollTo delegates to override when set", () => {
      const overrideScrollTo = vi.fn();
      const { setScrollOverride, scrollTo } = useActiveSection();

      setScrollOverride({
        scrollTo: overrideScrollTo,
        scrollToSection: () => false,
      });

      scrollTo(42);

      expect(overrideScrollTo).toHaveBeenCalledWith(42);
    });

    it("scrollToSection delegates to override when set", () => {
      const overrideScrollToSection = vi.fn(() => true);
      const { setScrollOverride, scrollToSection } = useActiveSection();

      setScrollOverride({
        scrollTo: vi.fn(),
        scrollToSection: overrideScrollToSection,
      });

      const result = scrollToSection("map-0");

      expect(overrideScrollToSection).toHaveBeenCalledWith("map-0");
      expect(result).toBe(true);
    });

    it("scrollTo falls back to no-op when no override", () => {
      const { scrollTo } = useActiveSection();

      // No override set — should not throw even with no registered elements
      expect(() => scrollTo(999)).not.toThrow();
    });

    it("clearing override restores default behavior", () => {
      const overrideScrollTo = vi.fn();
      const { setScrollOverride, scrollTo } = useActiveSection();

      setScrollOverride({
        scrollTo: overrideScrollTo,
        scrollToSection: () => false,
      });

      setScrollOverride(null);
      scrollTo(42);

      expect(overrideScrollTo).not.toHaveBeenCalled();
    });
  });
});

// ---------------------------------------------------------------------------
// Scroll spy integration: "when the user scrolls to X, which section highlights?"
// Mirrors the AlbumViewer watchEffect without needing a real virtualizer.
// ---------------------------------------------------------------------------

describe("active section highlighting", () => {
  // Standard album layout: 4 header pages (cover-front, cover-back, overview, full-map)
  // followed by step and map sections. Each page is 800px tall by default.
  function item(index: number, start: number, size = 800): VirtualItem {
    return { index, start, size };
  }
  const PAGE = 800;
  const headers = [item(0, 0), item(1, PAGE), item(2, PAGE * 2), item(3, PAGE * 3)];
  const sectionStart = PAGE * 4; // where content sections begin

  const stepSection = (id: number): Section => ({
    type: "step",
    step: makeStep({ id }),
  });
  const mapSection = (dateRange: DateRange): Section => ({
    type: "map",
    steps: [],
    segments: [],
    rangeIdx: 0,
    dateRange,
  });

  const HEADER_COUNT = HEADER_KEYS.length;

  /** Run the same logic as the AlbumViewer watchEffect. */
  function activeAt(
    vItems: VirtualItem[],
    sections: Section[],
    scrollY: number,
    viewportHeight = 800,
  ) {
    const { setActive, activeStepId, activeSectionKey, resetActiveSection } = useActiveSection();
    const best = pickBestItem(vItems, scrollY, 0, viewportHeight / 2);
    let id: number | string | null = null;
    if (best) {
      if (best.index < HEADER_COUNT) id = HEADER_KEYS[best.index] ?? null;
      else id = activeSectionId(sections, best.index - HEADER_COUNT) ?? null;
    }
    setActive(id);
    const result = { stepId: activeStepId.value, sectionKey: activeSectionKey.value };
    resetActiveSection();
    return result;
  }

  it("highlights the cover at the top of the page", () => {
    const vItems = [...headers, item(4, sectionStart)];
    const result = activeAt(vItems, [stepSection(1)], 0);
    expect(result.sectionKey).toBe("cover-front");
  });

  it("highlights a step when it dominates the viewport", () => {
    const vItems = [...headers, item(4, sectionStart)];
    const result = activeAt(vItems, [stepSection(42)], sectionStart - 100);
    expect(result.stepId).toBe(42);
  });

  it("highlights a map section when it dominates the viewport", () => {
    const range: DateRange = ["2024-01-01", "2024-01-15"];
    const vItems = [...headers, item(4, sectionStart), item(5, sectionStart + PAGE)];
    const result = activeAt(vItems, [mapSection(range), stepSection(1)], sectionStart - 100);
    expect(result.sectionKey).toMatch(/^map-/);
  });

  it("transitions through sections as the user scrolls down", () => {
    const vItems = [...headers, item(4, sectionStart)];
    const sections = [stepSection(55)];

    expect(activeAt(vItems, sections, 0).sectionKey).toBe("cover-front");
    expect(activeAt(vItems, sections, PAGE * 2 + 100).sectionKey).toBe("overview");
    expect(activeAt(vItems, sections, sectionStart - 100).stepId).toBe(55);
  });

  it("section barely visible at top does not steal highlight from section filling the viewport", () => {
    // User scrolled so overview is almost off the top, full-map fills the screen.
    // This is the exact scenario from the bug report screenshot.
    const vItems = [...headers, item(4, sectionStart)];
    const sections = [stepSection(1)];

    // Overview (index 2) has ~100px left on screen, full-map (index 3) fills the rest.
    const result = activeAt(vItems, sections, PAGE * 2 + 700);
    expect(result.sectionKey).toBe("full-map");
  });

  it("tall map mostly scrolled off does not steal highlight from visible step", () => {
    // Regression: a tall hike map that's mostly scrolled off should lose to
    // the step that's actually dominating the viewport.
    const tallMap = item(4, sectionStart, 1200);
    const step = item(5, sectionStart + 1200, PAGE);
    const vItems = [...headers, tallMap, step];
    const range: DateRange = ["2024-01-01", "2024-01-15"];
    const sections = [mapSection(range), stepSection(42)];

    // Scrolled far enough that only ~200px of the map remains on screen.
    const result = activeAt(vItems, sections, sectionStart + 1000);
    expect(result.stepId).toBe(42);
  });

  it("returns null when no items exist", () => {
    const result = activeAt([], [], 0);
    expect(result.stepId).toBeNull();
    expect(result.sectionKey).toBeNull();
  });

  it("returns null for out-of-bounds virtualizer index", () => {
    const result = activeAt([item(100, 0)], [], 0);
    expect(result.stepId).toBeNull();
    expect(result.sectionKey).toBeNull();
  });
});
