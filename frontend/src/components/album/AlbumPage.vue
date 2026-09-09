<script setup lang="ts">
withDefaults(defineProps<{ numberPlacement?: "margin" | "image" | "none" }>(), {
  numberPlacement: "margin",
});
</script>

<template>
  <div class="page-container" :class="`number-${numberPlacement}`">
    <slot />
    <span
      v-if="numberPlacement !== 'none'"
      class="album-page-number"
      aria-hidden="true"
    />
  </div>
</template>

<style scoped>
.page-container {
  position: relative;
  width: var(--page-width);
  height: var(--page-height);
  background-color: var(--page-bg, var(--bg));
  font-family: var(--font-album);
  contain: strict;
}

:slotted(.page-content) {
  padding-bottom: var(--page-content-inset-bottom);
}

.number-margin > :slotted(.page-content) {
  padding-bottom: calc(
    var(--page-content-inset-bottom) + var(--page-number-clearance, 0mm)
  );
}

.album-page-number {
  display: var(--page-number-display, none);
  position: absolute;
  inset-block-end: max(5mm, var(--safe-margin, 0mm));
  inset-inline: 0;
  margin-inline: auto;
  width: max-content;
  z-index: 3;
  color: var(--text-muted);
  font: 500 3.2mm / 1 var(--font-album);
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}

.number-image > .album-page-number {
  color: var(--text-on-color);
  text-shadow:
    0 0.2mm 0.5mm #000,
    0 0.1mm 0.15mm #000;
}

.album-page-number::after {
  counter-reset: album-page var(--page-number);
  content: counter(album-page);
}
</style>
