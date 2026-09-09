<template>
  <div class="page-container">
    <slot />
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
</style>
