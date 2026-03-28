<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import { onMounted, onUnmounted, ref } from "vue";

defineProps<{
  /** Number of album pages in this section (drives placeholder height). */
  pageCount?: number;
  /** Whether this section includes editor-only chrome (add-zone, unused tray). */
  hasChrome?: boolean;
}>();

const printMode = usePrintMode();
const el = ref<HTMLElement>();
const mounted = ref(printMode);

let observer: IntersectionObserver | null = null;
let unmountTimer = 0;

onMounted(() => {
  if (printMode || !el.value) return;

  observer = new IntersectionObserver(
    ([entry]) => {
      if (!entry) return;
      if (entry.isIntersecting) {
        clearTimeout(unmountTimer);
        mounted.value = true;
      } else {
        unmountTimer = window.setTimeout(() => { mounted.value = false; }, 500);
      }
    },
    {
      root: null,
      rootMargin: "150% 0px",
    },
  );
  observer.observe(el.value);
});

onUnmounted(() => {
  clearTimeout(unmountTimer);
  observer?.disconnect();
});
</script>

<template>
  <div
    ref="el"
    :aria-busy="!mounted ? 'true' : undefined"
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
    var(--section-pages, 1) * (var(--page-height) * var(--editor-zoom, 1) + var(--gap-md-lg))
    + var(--section-chrome, 0rem)
  );
}

/* Mounted: content-visibility lets the browser skip rendering for
   off-screen sections without destroying the DOM. */
.lazy-section {
  content-visibility: auto;
  contain-intrinsic-height: auto calc(
    var(--section-pages, 1) * (var(--page-height) * var(--editor-zoom, 1) + var(--gap-md-lg))
  );
}
</style>
