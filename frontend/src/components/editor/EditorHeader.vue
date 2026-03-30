<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import UserMenu from "./UserMenu.vue";

const { t } = useI18n();
</script>

<template>
  <q-header class="editor-header row no-wrap items-center">
    <div class="header-brand row no-wrap items-center q-gutter-x-sm">
      <img src="/logo.svg" alt="" class="header-logo" />
      <span class="header-title text-body1 text-weight-semibold text-bright">{{ t("brand") }}</span>
    </div>

    <div class="header-center row no-wrap justify-center">
      <slot />
    </div>

    <UserMenu />
  </q-header>
</template>

<style lang="scss" scoped>
.editor-header {
  padding: var(--gap-md) var(--gap-md-lg) var(--gap-md) 1.25rem; // optical alignment — no matching gap token
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
