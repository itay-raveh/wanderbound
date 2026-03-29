---
paths:
  - "frontend/src/components/album/**"
  - "frontend/src/pages/PrintView.vue"
---

# Print-Safe CSS

Album components render in Chromium's PDF backend (Skia) via Playwright `page.pdf()`.

## Genuinely broken — avoid entirely

- backdrop-filter → not supported (Skia can't composite backdrop)
- mix-blend-mode / background-blend-mode → unreliable, use solid colors
- mask-image (CSS masks) → dropped by Skia; use clip-path instead
- position: fixed → repeats on every page (use absolute or static)

## Work but get rasterized — use sparingly

Skia's PDF backend expands these to bitmaps. Visually correct, but text inside
loses selectability and file size increases. Acceptable for small decorative
elements; avoid on large areas or text-heavy containers.

- box-shadow → rasterizes the element; prefer border/outline for large elements
- filter (blur, drop-shadow, brightness, etc.) → rasterized
- SVG filters (feGaussianBlur, etc.) → rasterized

## Work natively — safe to use

- opacity (any value, any size) → native PDF graphics state
- CSS gradients (any number of stops) → native PDF shading objects
- clip-path (basic shapes) → native
- transform: scale() → works with `contain: size` on the container

## Prerequisites (required for all of the above)

- `print-color-adjust: exact` on elements with background colors/images/gradients
- `printBackground: true` in Playwright `page.pdf()` options
- Disable animations: `@media print { * { animation: none !important; transition: none !important; } }`

## WebGL / Mapbox GL maps

Canvas content from WebGL is blank in headless PDF by default. Our pipeline
captures map tiles via CDP and composites them as static images before print.
Any new map rendering must go through this pipeline — never rely on live WebGL
canvas for PDF output.

Test PDF output after any visual changes to album components.
