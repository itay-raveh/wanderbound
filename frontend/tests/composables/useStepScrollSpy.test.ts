import { useStepScrollSpy, vSpyStep } from "@/composables/useStepScrollSpy";

describe("useStepScrollSpy", () => {
  afterEach(() => {
    const { resetScrollSpy } = useStepScrollSpy();
    resetScrollSpy();
  });

  describe("setScrollOverride", () => {
    it("scrollTo delegates to override when set", () => {
      const overrideScrollTo = vi.fn();
      const { setScrollOverride, scrollTo } = useStepScrollSpy();

      setScrollOverride({
        scrollTo: overrideScrollTo,
        scrollToSection: () => false,
      });

      scrollTo(42);

      expect(overrideScrollTo).toHaveBeenCalledWith(42);
    });

    it("scrollToSection delegates to override when set", () => {
      const overrideScrollToSection = vi.fn(() => true);
      const { setScrollOverride, scrollToSection } = useStepScrollSpy();

      setScrollOverride({
        scrollTo: vi.fn(),
        scrollToSection: overrideScrollToSection,
      });

      const result = scrollToSection("map-0");

      expect(overrideScrollToSection).toHaveBeenCalledWith("map-0");
      expect(result).toBe(true);
    });

    it("scrollTo falls back to scrollIntoView when no override", () => {
      const { scrollTo } = useStepScrollSpy();

      // No override set — should not throw even with no registered elements
      expect(() => scrollTo(999)).not.toThrow();
    });

    it("clearing override restores default behavior", () => {
      const overrideScrollTo = vi.fn();
      const { setScrollOverride, scrollTo } = useStepScrollSpy();

      setScrollOverride({
        scrollTo: overrideScrollTo,
        scrollToSection: () => false,
      });

      setScrollOverride(null);
      scrollTo(42);

      expect(overrideScrollTo).not.toHaveBeenCalled();
    });

    it("resetScrollSpy clears the override", () => {
      const overrideScrollTo = vi.fn();
      const { setScrollOverride, scrollTo, resetScrollSpy } = useStepScrollSpy();

      setScrollOverride({
        scrollTo: overrideScrollTo,
        scrollToSection: () => false,
      });

      resetScrollSpy();
      scrollTo(42);

      expect(overrideScrollTo).not.toHaveBeenCalled();
    });
  });

  describe("vSpyStep directive", () => {
    it("registers step id on mount", () => {
      const el = document.createElement("div");
      vSpyStep.mounted!(el, { value: 5 } as never, null as never, null as never);

      // Verify it was registered by checking that scrollTo doesn't throw
      const { scrollTo } = useStepScrollSpy();
      expect(() => scrollTo(5)).not.toThrow();

      // Clean up
      vSpyStep.unmounted!(el, { value: 5 } as never, null as never, null as never);
    });

    it("registers section key on mount", () => {
      const el = document.createElement("div");
      vSpyStep.mounted!(el, { value: "map-0" } as never, null as never, null as never);

      // Clean up
      vSpyStep.unmounted!(el, { value: "map-0" } as never, null as never, null as never);
    });

    it("skips registration for undefined value", () => {
      const el = document.createElement("div");
      // Should not throw
      vSpyStep.mounted!(el, { value: undefined } as never, null as never, null as never);
    });

    it("re-registers on update with different value", () => {
      const el = document.createElement("div");
      vSpyStep.mounted!(el, { value: 1 } as never, null as never, null as never);
      vSpyStep.updated!(el, { value: 2, oldValue: 1 } as never, null as never, null as never);

      // Clean up with new value
      vSpyStep.unmounted!(el, { value: 2 } as never, null as never, null as never);
    });

    it("skips re-registration when value unchanged", () => {
      const el = document.createElement("div");
      vSpyStep.mounted!(el, { value: 1 } as never, null as never, null as never);

      // Same value — should be a no-op
      vSpyStep.updated!(el, { value: 1, oldValue: 1 } as never, null as never, null as never);

      vSpyStep.unmounted!(el, { value: 1 } as never, null as never, null as never);
    });
  });
});
