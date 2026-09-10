<script setup lang="ts">
defineOptions({ inheritAttrs: false });
defineProps<{ cover?: boolean; widthMm?: number }>();
</script>

<template>
  <div
    class="page-container"
    :class="{ 'cover-sheet': cover }"
    :style="widthMm ? { '--trim-width': `${widthMm}mm` } : undefined"
  >
    <div class="page-artwork" v-bind="$attrs"><slot /></div>
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
</style>
