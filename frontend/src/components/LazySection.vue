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
  if (printMode || props.eager || !el.value) return;
  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry) visible.value = entry.isIntersecting;
    },
    // Mount 2 viewport-heights before visible, unmount when scrolled beyond.
    // Prevents WebGL context exhaustion from too many simultaneous maps.
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
.lazy-placeholder {
  min-height: calc(
    var(--section-pages, 1) * (var(--page-height) * var(--editor-zoom, 1) + 0.75rem)
    + var(--section-chrome, 0rem)
  );
}
</style>
