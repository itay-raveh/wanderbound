---
paths:
  - "frontend/src/components/album/**"
  - "frontend/src/pages/PrintView.vue"
---

# Print-safe CSS

Album components render through Chromium's Skia PDF path. Preview and PDF must
show the same album. Print-only CSS may hide editor controls, handles, and
overlays, but must not change album content, spacing, effects, or pagination.

## Avoid

- `backdrop-filter`, blend modes, and CSS masks;
- `position: fixed`, which repeats content on every page;
- the `transparent` gradient keyword, which interpolates through transparent
  black;
- alpha inside CSS gradient stops, including `rgb(var(--x) / alpha)`;
- large shadows or filters around text-heavy containers, which rasterize them.

## Prefer

- solid CSS gradient stops;
- inline SVG gradients with `stop-opacity` for fades;
- a separate background element with CSS `opacity` for translucent solid fills;
- `clip-path`, transforms, borders, and outlines;
- `currentColor` when an SVG gradient must inherit a theme token.

Small decorative shadows and filters are acceptable when rasterization does not
harm text selection or file size. Test actual PDF output after changing album
visuals. Existing examples live in `ElevationProfile.vue` and `HikeMapPage.vue`.
