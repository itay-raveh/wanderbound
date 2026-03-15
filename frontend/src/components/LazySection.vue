<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import { SCROLL_CONTAINER_KEY } from "@/composables/useScrollContainer";
import { inject, onMounted, onUnmounted, ref } from "vue";

const props = defineProps<{
  /** Number of album pages in this section (drives placeholder height). */
  pageCount?: number;
  /** Whether this section includes editor-only chrome (add-zone, unused tray). */
  hasChrome?: boolean;
  /** Skip lazy loading — mount content immediately. */
  eager?: boolean;
}>();

const printMode = usePrintMode();
const scrollContainer = inject(SCROLL_CONTAINER_KEY, ref(undefined));
const el = ref<HTMLElement>();
const mounted = ref(printMode || props.eager);

let observer: IntersectionObserver | null = null;

onMounted(() => {
  if (mounted.value || !el.value) return;
  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry?.isIntersecting) {
        mounted.value = true;
        observer!.disconnect();
        observer = null;
      }
    },
    {
      root: scrollContainer.value ?? null,
      rootMargin: "200% 0px",
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
      'lazy-section': mounted,
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
/* Before first mount: fixed-height placeholder so scroll position is stable. */
.lazy-placeholder {
  min-height: calc(
    var(--section-pages, 1) * (var(--page-height) * var(--editor-zoom, 1) + 0.75rem)
    + var(--section-chrome, 0rem)
  );
}

/* After mount: content-visibility lets the browser skip rendering for
   off-screen sections without destroying the DOM (no unmount/remount jank). */
.lazy-section {
  content-visibility: auto;
  contain-intrinsic-height: auto calc(
    var(--section-pages, 1) * (var(--page-height) * var(--editor-zoom, 1) + 0.75rem)
  );
}
</style>
