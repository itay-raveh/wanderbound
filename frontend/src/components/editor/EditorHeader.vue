<script lang="ts" setup>
import UserMenu from "./UserMenu.vue";
</script>

<template>
  <header class="editor-header">
    <div class="header-brand">
      <img src="/logo.svg" alt="Logo" class="header-logo" />
      <span class="header-title">Polarsteps Album Generator</span>
    </div>

    <UserMenu />
  </header>
</template>

<style lang="scss" scoped>
.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem 0.5rem 1.25rem;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.header-logo {
  width: 1.625rem;
  height: 1.625rem;
}

.header-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-bright);
  letter-spacing: -0.01em;
}
</style>
