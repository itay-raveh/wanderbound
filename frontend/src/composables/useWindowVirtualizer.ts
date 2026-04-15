/**
 * Drop-in replacement for @tanstack/vue-virtual's useWindowVirtualizer.
 *
 * The upstream adapter wraps the Virtualizer in a shallowRef and calls
 * triggerRef() on every change. Vue 3.4+'s computed deduplication treats a
 * same-reference shallowRef as unchanged, so downstream computeds and the
 * render effect never re-run (vuejs/core#9579, #11929, #8036).
 *
 * This adapter avoids shallowRef+triggerRef entirely. It holds the Virtualizer
 * in a plain variable and exposes pre-computed reactive refs for the two values
 * templates actually need: virtualItems and totalSize. A regular ref<number>
 * version counter drives reactivity — the most fundamental primitive that
 * Vue's scheduler cannot skip.
 *
 * When @tanstack/vue-virtual fixes its shallowRef+triggerRef pattern
 * (tracked in TanStack/virtual — no issue filed yet as of March 2026),
 * delete this file and switch back to the upstream useWindowVirtualizer.
 */
import {
  Virtualizer,
  observeWindowOffset,
  observeWindowRect,
  windowScroll,
  type PartialKeys,
  type VirtualizerOptions,
  type VirtualItem,
} from "@tanstack/vue-virtual";
import { computed, onScopeDispose, ref, unref, watch, type MaybeRef } from "vue";

type WindowVirtualizerOpts = PartialKeys<
  VirtualizerOptions<Window, Element>,
  "observeElementRect" | "observeElementOffset" | "scrollToFn" | "getScrollElement"
>;

/**
 * Cancel the virtualizer's internal scroll reconciliation loop.
 *
 * When `scrollToIndex` is called with `behavior: "smooth"`, the virtualizer
 * runs a rAF loop (up to 5 s) that re-scrolls toward the target on every
 * frame. If the user manually scrolls away during that window, the loop
 * fights them - the page snaps back to the programmatic target.
 *
 * `scrollState` is TypeScript `private` (erased at runtime), so we can null
 * it directly to stop the loop. This is the only reliable cancellation
 * mechanism - the library exposes no public API for it.
 */
function cancelProgrammaticScroll(v: Virtualizer<Window, Element>) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (v as any).scrollState = null;
}

export function useWindowVirtualizer(options: MaybeRef<WindowVirtualizerOpts>) {
  const version = ref(0);

  function bump() {
    version.value++;
  }

  function resolveOptions(): VirtualizerOptions<Window, Element> {
    const opts = unref(options);
    return {
      getScrollElement: () => (typeof document !== "undefined" ? window : null),
      observeElementRect: observeWindowRect,
      observeElementOffset: observeWindowOffset,
      scrollToFn: windowScroll,
      initialOffset: () => (typeof document !== "undefined" ? window.scrollY : 0),
      ...opts,
      onChange: (instance: Virtualizer<Window, Element>, sync: boolean) => {
        bump();
        opts.onChange?.(instance, sync);
      },
    };
  }

  const virtualizer = new Virtualizer<Window, Element>(resolveOptions());
  const cleanup = virtualizer._didMount();

  // Cancel programmatic scroll when user manually scrolls (wheel or touch).
  // Without this, virtualizer.scrollToIndex with smooth behavior fights the
  // user for up to 5 seconds.
  const onUserScroll = () => cancelProgrammaticScroll(virtualizer);
  window.addEventListener("wheel", onUserScroll, { passive: true });
  window.addEventListener("touchmove", onUserScroll, { passive: true });

  watch(
    () => unref(options),
    () => {
      virtualizer.setOptions(resolveOptions());
      virtualizer._willUpdate();
      bump();
    },
  );

  onScopeDispose(() => {
    cleanup();
    window.removeEventListener("wheel", onUserScroll);
    window.removeEventListener("touchmove", onUserScroll);
  });

  const items = computed<VirtualItem[]>(() => {
    void version.value;
    return virtualizer.getVirtualItems();
  });

  const size = computed<number>(() => {
    void version.value;
    return virtualizer.getTotalSize();
  });

  return { virtualizer, items, size, version };
}
