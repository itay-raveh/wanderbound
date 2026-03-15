<script lang="ts" setup>
import { RouterView } from "vue-router";
</script>

<template>
  <q-layout>
    <q-page-container>
      <RouterView />
    </q-page-container>
  </q-layout>
</template>

<style lang="scss">
/* Design tokens (theme-independent) */

:root {
  /* A4 landscape page dimensions (single source of truth for album pages). */
  --page-width: 297mm;
  --page-height: 210mm;

  /* Type scale — derived from Quasar SASS overrides in quasar-variables.sass. */
  --text-sm: #{$caption-font-size};
  --text-base: #{$body2-font-size};
  --text-md: #{$subtitle2-font-size};

  /* Border radius */
  --radius-sm: 0.375rem;
  --radius-md: 0.625rem;
  --radius-lg: 1rem;
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
