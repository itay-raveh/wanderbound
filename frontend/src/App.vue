<script lang="ts" setup>
import { RouterView } from "vue-router";
import { useMeta } from "quasar";
import ScreenGuard from "@/components/ScreenGuard.vue";
import SiteFooter from "@/components/SiteFooter.vue";

useMeta({
  titleTemplate: (title) => (title ? `${title} | Wanderbound` : "Wanderbound"),
});
</script>

<template>
  <ScreenGuard>
    <a href="#main-content" class="skip-to-content">Skip to content</a>
    <q-layout view="hHh lpr lff">
      <q-page-container id="main-content">
        <RouterView />
        <SiteFooter class="print-hide" />
      </q-page-container>
    </q-layout>
  </ScreenGuard>
</template>

<style lang="scss">
html,
body,
#app {
  height: 100%;
  margin: 0;
}

/* Design tokens (theme-independent) */

:root {
  /* Font stacks - self-hosted in fonts.css. Quasar's $typography-font-family
     (quasar-variables.sass) mirrors --font-body at build time; keep them in sync. */
  --font-body: "Inter", system-ui, -apple-system, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;

  /* A4 landscape page dimensions (single source of truth for album pages). */
  --page-width: 297mm;
  --page-height: 210mm;
  --page-aspect: 297 / 210;

  /* Step page layout: meta-panel occupies this fraction of the page width. */
  --meta-ratio: 0.42;

  /* Border radius scale */
  --radius-xs: 2px;
  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
  --radius-xl: 1rem;
  --radius-full: 999px;

  /* Page typography scale (album pages - beyond Quasar's 12 type levels) */
  --display-1: 3.75rem;
  --display-2: 3rem;
  --type-2xl: 1.75rem;
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
  --gap-md-lg: 0.75rem;
  --gap-md: 0.5rem;
  --gap-sm-md: 0.375rem;
  --gap-sm: 0.25rem;
  --gap-xs: 0.125rem;

  /* Photo grid gaps */
  --photo-gap-lg: 5mm;
  --photo-gap-md: 4mm;
  --photo-gap-sm: 3mm;
  --photo-gap-xs: 2mm;

  /* Transition / animation */
  --duration-fast: 0.15s;
  --duration-normal: 0.3s;
  --duration-slow: 0.5s;
}

/* Accent card - overview record/furthest panels.
   Set --accent on the element to control the accent color. */
.accent-card {
  padding: 0.625rem var(--gap-md-lg);
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

/* Two-column text body - single source of truth for step descriptions and
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
  color-scheme: dark;
  --page-bg: #1e1e2e;
  --bg: #1e1e2e;
  --bg-secondary: #252540;
  --bg-deep: #0a0a12;
  --text: #e5e7eb;
  --text-bright: #f0f0f5;
  --text-muted: #9ca3af;
  --text-faint: #6b7280;
  --danger: #ef4444;
  --surface: #2a2a3e;
  --border-color: #3a3a50;
  --shadow-sm: 0 1px 4px rgba(0, 0, 0, 0.25);
  --shadow-md: 0 4px 20px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 12px 36px rgba(0, 0, 0, 0.55);
  --page-gradient: linear-gradient(
    to bottom,
    color-mix(in srgb, var(--q-primary) 8%, var(--bg-deep)),
    var(--bg)
  );
}

/* Custom color palette - follows Quasar convention (see quasar.dev/style/color-palette#adding-your-own-colors).
   !important matches Quasar's own color classes; `color="danger"` works on QBtn/QIcon/etc. */
.text-bright {
  color: var(--text-bright) !important;
}
.text-muted {
  color: var(--text-muted) !important;
}
.text-faint {
  color: var(--text-faint) !important;
}
.text-danger {
  color: var(--danger) !important;
}
.bg-danger {
  background: var(--danger) !important;
}
.bg-surface {
  background: var(--surface) !important;
}

.body--light {
  color-scheme: light;
  --page-bg: #ffffff;
  --bg: #f3f4f6;
  --bg-secondary: #ffffff;
  --bg-deep: #dce1e8;
  --text: #1f2937;
  --text-bright: #111827;
  --text-muted: #5d646f;
  --text-faint: #9ca3af;
  --danger: #dc2626;
  --surface: #f3f4f6;
  --border-color: #d1d5db;
  --shadow-sm: 0 1px 4px rgba(0, 0, 0, 0.08);
  --shadow-md: 0 4px 20px rgba(0, 0, 0, 0.15);
  --shadow-lg: 0 12px 36px rgba(0, 0, 0, 0.22);
  --page-gradient: linear-gradient(
    to bottom,
    color-mix(in srgb, var(--q-primary) 14%, var(--bg-deep)),
    var(--bg)
  );
}

/* Skip-to-content link — visible only on keyboard focus */
.skip-to-content {
  position: absolute;
  width: 1px;
  height: 1px;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  overflow: hidden;
  white-space: nowrap;
  z-index: 9999;

  &:focus {
    position: fixed;
    top: 0.5rem;
    left: 0.5rem;
    width: auto;
    height: auto;
    padding: 0.5rem 1rem;
    background: var(--bg-secondary);
    color: var(--text);
    border: 2px solid var(--q-primary);
    border-radius: var(--radius-md);
    font-size: var(--type-sm);
    text-decoration: none;
  }
}
</style>
