<script lang="ts" setup>
import { RouterView } from "vue-router";
</script>

<template>
  <RouterView />
</template>

<style lang="scss">
/* Prevent page-level scroll — each view manages its own scroll container. */
html, body, #app {
  height: 100%;
  margin: 0;
  overflow: hidden;
}

/* Design tokens (theme-independent) */

:root {
  /* A4 landscape page dimensions (single source of truth for album pages). */
  --page-width: 297mm;
  --page-height: 210mm;
}

/* Theme colors */

.body--dark {
  --page-bg: #1E1E2E;
  --bg: #1E1E2E;
  --bg-secondary: #252540;
  --bg-deep: #0a0a12;
  --text: #E5E7EB;
  --text-bright: #F0F0F5;
  --text-muted: #9CA3AF;
  --text-faint: #6B7280;
  --accent-light: #60A5FA;
  --danger: #EF4444;
  --surface: #2A2A3E;
  --border-color: #3A3A50;
}

.body--light {
  --page-bg: #FFFFFF;
  --bg: #F3F4F6;
  --bg-secondary: #FFFFFF;
  --bg-deep: #E5E7EB;
  --text: #1F2937;
  --text-bright: #111827;
  --text-muted: #6B7280;
  --text-faint: #9CA3AF;
  --accent-light: #2563EB;
  --danger: #DC2626;
  --surface: #F3F4F6;
  --border-color: #D1D5DB;
}
</style>
