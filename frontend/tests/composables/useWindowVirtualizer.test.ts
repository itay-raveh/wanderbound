import { computed, nextTick, ref } from "vue";
import { useWindowVirtualizer } from "@/composables/useWindowVirtualizer";
import { withSetup } from "../helpers";

// Mock the window scroll functions from @tanstack/vue-virtual
vi.mock("@tanstack/vue-virtual", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/vue-virtual")>();
  return {
    ...actual,
    observeWindowRect: vi.fn((_instance, cb) => {
      // Simulate an initial rect callback
      cb({ width: 1024, height: 768 });
      return () => {};
    }),
    observeWindowOffset: vi.fn((_instance, cb) => {
      cb(0, false);
      return () => {};
    }),
    windowScroll: vi.fn(),
  };
});

describe("useWindowVirtualizer", () => {
  it("returns virtualizer instance, items, and size", () => {
    const { virtualizer, items, size } = withSetup(() =>
      useWindowVirtualizer(
        computed(() => ({
          count: 10,
          estimateSize: () => 100,
          overscan: 3,
        })),
      ),
    );

    expect(virtualizer).toBeDefined();
    expect(virtualizer.options).toBeDefined();
    expect(items.value).toBeInstanceOf(Array);
    expect(typeof size.value).toBe("number");
  });

  it("virtualizer is a plain object, not a Vue ref", () => {
    const { virtualizer } = withSetup(() =>
      useWindowVirtualizer(
        computed(() => ({
          count: 5,
          estimateSize: () => 50,
        })),
      ),
    );

    // Should be the raw Virtualizer, not wrapped in a ref
    expect(virtualizer.constructor.name).toBe("Virtualizer");
    // Should have methods directly accessible (no .value)
    expect(typeof virtualizer.getVirtualItems).toBe("function");
    expect(typeof virtualizer.getTotalSize).toBe("function");
    expect(typeof virtualizer.scrollToIndex).toBe("function");
  });

  it("updates items and size when options change", async () => {
    const count = ref(5);

    const { size } = withSetup(() =>
      useWindowVirtualizer(
        computed(() => ({
          count: count.value,
          estimateSize: () => 100,
          overscan: 5,
        })),
      ),
    );

    const initialSize = size.value;

    count.value = 20;
    await nextTick();

    // Size should increase with more items
    expect(size.value).toBeGreaterThan(initialSize);
  });

  it("calls user-provided onChange alongside internal bump", () => {
    const onChangeSpy = vi.fn();

    const { virtualizer } = withSetup(() =>
      useWindowVirtualizer(
        computed(() => ({
          count: 10,
          estimateSize: () => 100,
          onChange: onChangeSpy,
        })),
      ),
    );

    // The watch with immediate: true triggers onChange once during setup
    const callsBefore = onChangeSpy.mock.calls.length;

    // Trigger onChange through the virtualizer's internal mechanism
    virtualizer.options.onChange?.(virtualizer, false);

    expect(onChangeSpy).toHaveBeenCalledTimes(callsBefore + 1);
    expect(onChangeSpy).toHaveBeenLastCalledWith(virtualizer, false);
  });

  it("items computed is reactive via version counter", () => {
    const { virtualizer, items } = withSetup(() =>
      useWindowVirtualizer(
        computed(() => ({
          count: 10,
          estimateSize: () => 100,
          overscan: 5,
        })),
      ),
    );

    // Access items to create the dependency
    expect(items.value).toBeInstanceOf(Array);

    // Trigger onChange (which bumps the version counter)
    virtualizer.options.onChange?.(virtualizer, false);

    // The computed should still return valid items
    expect(items.value).toBeInstanceOf(Array);
  });
});
