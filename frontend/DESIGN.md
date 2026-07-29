---
name: Wanderbound
description: A quiet print studio for turning trips into editable, print-ready albums.
colors:
  primary: "#0063D1"
  accent: "#2D254C"
  dark-page: "#1E1E2E"
  dark-surface: "#2A2A3E"
  dark-text: "#E5E7EB"
  light-workspace: "#F3F4F6"
  light-surface: "#FFFFFF"
  light-text: "#1F2937"
  light-border: "#D1D5DB"
  danger-light: "#DC2626"
  danger-dark: "#EF4444"
typography:
  ui:
    fontFamily: "Assistant, system-ui, -apple-system, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  title:
    fontFamily: "Assistant, system-ui, -apple-system, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.2
  album-body:
    fontFamily: "Frank Ruhl Libre, Georgia, serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.65
rounded:
  xs: "0.125rem"
  sm: "0.375rem"
  md: "0.5rem"
  lg: "0.75rem"
  xl: "1rem"
  full: "999px"
spacing:
  xs: "0.125rem"
  sm: "0.25rem"
  sm-md: "0.375rem"
  md: "0.5rem"
  md-lg: "0.75rem"
  lg: "1rem"
components:
  primary-action:
    backgroundColor: "{colors.primary}"
    textColor: "#F0F0F5"
    typography: "{typography.ui}"
    rounded: "{rounded.md}"
  editor-surface:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.xl}"
  album-page:
    width: "297mm"
    height: "210mm"
---

# Design System: Wanderbound

## 1. Overview

Wanderbound is a quiet print studio. Application chrome is compact, cool-toned,
and restrained so photographs, maps, and the physical album remain dominant.
It should feel dependable rather than playful, decorative, or professionally
dense.

The live source of truth for tokens is `src/App.vue`; Quasar brand colors live
in `src/main.ts`. Update this document when those design decisions change.

## 2. Colors

Atlas Blue is the single interaction signal for primary actions, selection,
progress, and focus. Violet is a supporting brand color, not a second action
color. Neutral surfaces establish hierarchy through tone and hairline borders.
Light and dark themes change values, never meaning or functionality.

## 3. Typography

Assistant owns application controls and album headings. Frank Ruhl Libre is
reserved for album narrative text. Use the type and font tokens from
`src/App.vue`; do not reproduce a separate local scale.

## 4. Elevation

Persistent UI is flat by default. Separate regions with tonal changes or
hairline borders. Shadows are reserved for selected controls, album-page
previews, menus, and dialogs. Avoid large effects in album output because the
PDF renderer may rasterize them.

## 5. Components

Controls are familiar, compact, keyboard-visible, and equivalent across light,
dark, LTR, and RTL modes. Reuse shared components under `src/components/ui/`
and Quasar primitives before creating another interaction pattern.

The A4 landscape album page is the signature surface. Its preview and PDF must
remain visually identical. Album geometry uses millimeters; application UI uses
rem units.

## 6. Do's and Don'ts

- Do make the album, photograph, or map the dominant object.
- Do use Atlas Blue consistently for interaction and focus.
- Do preserve theme, direction, keyboard, and reduced-motion behavior.
- Do reuse live CSS tokens instead of copying their values into components.
- Don't turn the product into a scrapbook, template marketplace, or dense
  professional design tool.
- Don't add decorative shadows or competing accent colors.
- Don't change album content, spacing, effects, or pagination only for print.
