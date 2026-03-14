<script lang="ts" setup>
import { usePrintMode } from "@/composables/usePrintReady";
import { onMounted, onUnmounted, ref } from "vue";

const props = defineProps<{
  /** Number of album pages in this section (drives placeholder height). */
  pageCount?: number;
  /** Whether this section includes editor-only chrome (add-zone, unused tray). */
  hasChrome?: boolean;
  /** Skip lazy loading — mount content immediately. */
  eager?: boolean;
}>();

const printMode = usePrintMode();
const el = ref<HTMLElement>();
const visible = ref(printMode || props.eager);

let observer: IntersectionObserver | null = null;

onMounted(() => {
  if (printMode || !el.value) return;
  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry?.isIntersecting) {
        visible.value = true;
        observer?.disconnect();
      }
    },
    // Start mounting content 2 viewport-heights before it scrolls into view.
    { rootMargin: "200% 0px" },
  );
  observer.observe(el.value);
});

onUnmounted(() => observer?.disconnect());
</script>

<template>
  <div
    ref="el"
    :class="{ 'lazy-placeholder': !visible && pageCount }"
    :style="
      !visible && pageCount
        ? {
            '--section-pages': pageCount,
            '--section-chrome': hasChrome ? '10rem' : '0rem',
          }
        : undefined
    "
  >
    <slot v-if="visible" />
  </div>
</template>

<style scoped>
/*
 * Placeholder height derived from the same CSS values that size actual pages:
 *   page height = 210mm (A4 landscape height)
 *   editor zoom = var(--editor-zoom, 1)   (set on .album-container)
 *   margin      = 0.75rem per page
 * Plus optional editor chrome (add-zone + unused sidebar).
 */
.lazy-placeholder {
  min-height: calc(
    var(--section-pages, 1) * (210mm * var(--editor-zoom, 1) + 0.75rem)
    + var(--section-chrome, 0rem)
  );
}
</style>
