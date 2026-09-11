<script setup lang="ts">
defineOptions({ inheritAttrs: false });
withDefaults(
  defineProps<{
    cover?: boolean;
    widthMm?: number;
    numberPlacement?: "margin" | "image" | "none";
  }>(),
  { numberPlacement: "margin" },
);
</script>

<template>
  <div
    class="page-container"
    :class="{ 'cover-sheet': cover }"
    :style="widthMm ? { '--trim-width': `${widthMm}mm` } : undefined"
  >
    <div
      class="page-artwork"
      :class="`number-${numberPlacement}`"
      v-bind="$attrs"
    >
      <slot />
      <span
        v-if="!cover && numberPlacement !== 'none'"
        class="album-page-number"
        aria-hidden="true"
      />
    </div>
    <div class="trim-guide" aria-hidden="true" />
    <div class="safe-guide" aria-hidden="true" />
  </div>
</template>

<style scoped>
.page-container {
  --bleed: var(--interior-bleed, 0mm);
  --trim-width: var(--page-width);
  position: relative;
  width: calc(var(--trim-width) + 2 * var(--bleed));
  height: calc(var(--page-height) + 2 * var(--bleed));
  padding: var(--bleed);
  box-sizing: border-box;
  background-color: var(--page-bg, var(--bg));
  font-family: var(--font-album);
  overflow: hidden;
  page: interior;
}
.cover-sheet {
  --bleed: var(--cover-bleed, 0mm);
  page: cover;
}
.page-artwork {
  position: relative;
  width: var(--trim-width);
  height: var(--page-height);
  overflow: visible;
}
:slotted(.page-content) {
  padding-bottom: var(--page-content-inset-bottom);
}
.trim-guide,
.safe-guide {
  display: none;
  position: absolute;
  pointer-events: none;
  z-index: 50;
}
.trim-guide {
  inset: var(--bleed);
  border: 1px solid white;
  box-shadow: 0 0 0 1px black;
}
.safe-guide {
  inset: calc(var(--bleed) + var(--safe-margin, 0mm));
  border: 1px dashed white;
  box-shadow: 0 0 0 1px black;
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
