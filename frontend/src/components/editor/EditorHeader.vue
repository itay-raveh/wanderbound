<script lang="ts" setup>
import UserMenu from "./UserMenu.vue";
</script>

<template>
  <q-header class="editor-header row no-wrap items-center">
    <div class="header-brand row no-wrap items-center q-gutter-x-sm">
      <img src="/logo.svg" alt="Logo" class="header-logo" />
      <span class="header-title text-body1 text-weight-semibold text-bright">Polarsteps Album Generator</span>
    </div>

    <div class="header-center row no-wrap justify-center">
      <slot />
    </div>

    <UserMenu />
  </q-header>
</template>

<style lang="scss" scoped>
.editor-header {
  padding: 0.5rem 0.75rem 0.5rem 1.25rem;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.header-logo {
  width: 1.625rem;
  height: 1.625rem;
}

.header-title {
  letter-spacing: var(--tracking-tight);
}

.header-center {
  flex: 1;
  min-width: 0;
}
</style>
