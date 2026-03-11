<script lang="ts" setup>
import type { User } from "@/client";
import { useQuasar } from "quasar";
import UserMenu from "./UserMenu.vue";

defineProps<{
  user?: User;
  isKm: boolean;
  isCelsius: boolean;
}>();

defineEmits<{
  delete: [];
}>();

const $q = useQuasar();
</script>

<template>
  <header class="editor-header">
    <div class="header-left">
      <img src="/logo.svg" alt="Logo" class="header-logo" />
      <span class="header-title">Polarsteps Album Generator</span>
    </div>

    <div class="header-right">
      <button
        class="icon-btn"
        :title="$q.dark.isActive ? 'Switch to light mode' : 'Switch to dark mode'"
        @click="$q.dark.toggle()"
      >
        <q-icon :name="$q.dark.isActive ? 'light_mode' : 'dark_mode'" size="1.15rem" />
      </button>

      <UserMenu
        v-if="user"
        :user="user"
        :is-km="isKm"
        :is-celsius="isCelsius"
        @delete="$emit('delete')"
      />
    </div>
  </header>
</template>

<style lang="scss" scoped>
.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 1rem;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.header-left {
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

.header-right {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.icon-btn {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 0.375rem;
  color: var(--text-muted);
  transition: background 0.15s ease, color 0.15s ease;

  &:hover {
    background: var(--surface);
    color: var(--text);
  }
}
</style>
