<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import { onMounted, onUnmounted, ref } from "vue";

const props = defineProps<{
  /** Number of album pages in this section (drives placeholder height). */
  pageCount?: number;
  /** Whether this section includes editor-only chrome (add-zone, unused tray). */
  hasChrome?: boolean;
  /** Skip lazy loading — mount content immediately and never unmount. */
  eager?: boolean;
}>();

const printMode = usePrintMode();
const el = ref<HTMLElement>();
const mounted = ref(printMode || props.eager);

let observer: IntersectionObserver | null = null;

onMounted(() => {
  if (printMode || !el.value) return;

  // Eager sections mount immediately and never unmount.
  if (props.eager) return;

  // Single observer with a large margin. Sections mount when within ~3
  // viewports and unmount when beyond that. The large margin ensures
  // mount/unmount transitions happen far off-screen — the user never
  // sees placeholders flash during normal scrolling.
  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry) mounted.value = entry.isIntersecting;
    },
    {
      root: null,
      rootMargin: "300% 0px",
    },
  );
  observer.observe(el.value);
});

onUnmounted(() => observer?.disconnect());
</script>

<template>
  <div
    ref="el"
    :class="{
      'lazy-section': mounted && !printMode,
      'lazy-placeholder': !mounted && pageCount,
    }"
    :style="
      !mounted && pageCount
        ? {
            '--section-pages': pageCount,
            '--section-chrome': hasChrome ? '10rem' : '0rem',
          }
        : mounted && pageCount
          ? { '--section-pages': pageCount }
          : undefined
    "
  >
    <slot v-if="mounted" />
  </div>
</template>

<style scoped>
/* Unmounted: fixed-height placeholder so scroll position is stable. */
.lazy-placeholder {
  min-height: calc(
    var(--section-pages, 1) * (var(--page-height) * var(--editor-zoom, 1) + 0.75rem)
    + var(--section-chrome, 0rem)
  );
}

/* Mounted: content-visibility lets the browser skip rendering for
   off-screen sections without destroying the DOM. */
.lazy-section {
  content-visibility: auto;
  contain-intrinsic-height: auto calc(
    var(--section-pages, 1) * (var(--page-height) * var(--editor-zoom, 1) + 0.75rem)
  );
}
</style>
