<script lang="ts" setup>
import { RouterView } from "vue-router";
</script>

<template>
  <RouterView />
</template>

<style lang="scss">
html, body, #app {
  height: 100%;
  margin: 0;
}

/* Design tokens (theme-independent) */

:root {
  /* A4 landscape page dimensions (single source of truth for album pages). */
  --page-width: 297mm;
  --page-height: 210mm;

  /* Step page layout: meta-panel occupies this fraction of the page width. */
  --meta-ratio: 0.42;

  /* Border radius scale */
  --radius-xs: 2px;
  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
  --radius-xl: 1rem;
  --radius-full: 999px;

  /* Page typography scale (album pages — beyond Quasar's 12 type levels) */
  --display-1: 3.75rem;
  --display-2: 3rem;
  --type-xl: 1.375rem;
  --type-lg: 1.25rem;
  --type-subtitle: 1.1rem;
  --type-md: 1rem;
  --type-sm: 0.875rem;
  --type-xs: 0.75rem;
  --type-2xs: 0.6875rem;
  --type-3xs: 0.5625rem;

  /* Letter-spacing */
  --tracking-tight: -0.02em;
  --tracking-wide: 0.06em;
  --tracking-wider: 0.2em;

  /* Page spacing */
  --page-inset-x: 3rem;
  --page-inset-y: 2.5rem;
  --gap-lg: 1rem;
  --gap-md: 0.5rem;
  --gap-sm: 0.25rem;
  --gap-xs: 0.125rem;

  /* Photo grid gaps */
  --photo-gap-lg: 5mm;
  --photo-gap-md: 4mm;
  --photo-gap-sm: 3mm;
  --photo-gap-xs: 2mm;

  /* Map page tokens */
  --page-dark-surface: rgb(24, 24, 28);
  --page-dark-overlay: rgb(30, 30, 34);

  /* Transition / animation */
  --duration-fast: 0.15s;
  --duration-normal: 0.3s;
  --duration-slow: 0.5s;
}

/* Accent card — overview record/furthest panels.
   Set --accent on the element to control the accent color. */
.accent-card {
  padding: 0.625rem 0.75rem;
  border-left: 3px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 6%, var(--page-bg, var(--bg)));
  border-radius: var(--radius-sm);
}

.accent-card-tag {
  font-size: var(--type-3xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  color: var(--accent);
}

/* Two-column text body — single source of truth for step descriptions and
   text continuation pages.  useTextMeasure.ts measurement containers also
   reference this class so changing a value here automatically keeps layout
   measurement in sync with rendering. */
.text-body-columns {
  padding: var(--page-inset-y) var(--page-inset-x);
  font-size: var(--type-sm);
  line-height: 1.65;
  white-space: pre-wrap;
  text-align: justify;
  column-count: 2;
  column-gap: var(--page-inset-y);
  overflow: hidden;
  box-sizing: border-box;
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
  --danger: #EF4444;
  --surface: #2A2A3E;
  --border-color: #3A3A50;
}

/* Custom color palette — follows Quasar convention (see quasar.dev/style/color-palette#adding-your-own-colors).
   !important matches Quasar's own color classes; `color="danger"` works on QBtn/QIcon/etc. */
.text-bright { color: var(--text-bright) !important; }
.text-muted { color: var(--text-muted) !important; }
.text-faint { color: var(--text-faint) !important; }
.text-danger { color: var(--danger) !important; }
.bg-danger { background: var(--danger) !important; }
.bg-surface { background: var(--surface) !important; }

.body--light {
  --page-bg: #FFFFFF;
  --bg: #F3F4F6;
  --bg-secondary: #FFFFFF;
  --bg-deep: #E5E7EB;
  --text: #1F2937;
  --text-bright: #111827;
  --text-muted: #6B7280;
  --text-faint: #9CA3AF;
  --danger: #DC2626;
  --surface: #F3F4F6;
  --border-color: #D1D5DB;
}
</style>
