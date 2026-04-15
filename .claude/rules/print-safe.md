---
paths:
  - "frontend/src/components/album/**"
  - "frontend/src/pages/PrintView.vue"
---

# Print-Safe CSS

Album components render in Chromium's PDF backend (Skia) via Playwright `page.pdf()`.

## WYSIWYG - preview and print must be identical

Never conditionally alter album page visuals between editor preview and print mode. No `usePrintMode()` guards to strip effects, no `.print-mode` overrides that change design. If an effect can't render in PDF, don't use it in the editor either. The only acceptable print-mode differences are editor UI chrome (handles, dashed borders, interactive overlays).

## Genuinely broken - avoid entirely

- backdrop-filter → not supported (Skia can't composite backdrop)
- mix-blend-mode / background-blend-mode → unreliable, use solid colors
- mask-image (CSS masks) → dropped by Skia; use clip-path instead
- position: fixed → repeats on every page (use absolute or static)
- color-mix() → Skia can't resolve it in the PDF paint path; produces wrong colors
- rgb(from …) (relative color syntax) → same issue as color-mix; broken in PDF
- `transparent` keyword in gradients → resolves to transparent black rgba(0,0,0,0);
  interpolating from a non-black color toward transparent black shifts the hue
- rgb(var(--XX-rgb) / alpha) → Skia renders this pink; the space-separated
  channel trick does NOT work for PDF despite working in-browser
- Any CSS alpha in gradients → Skia's PDF paint path breaks alpha in gradient
  color stops. Use SVG `stop-opacity` instead (see below)

## Work but get rasterized - use sparingly

Skia's PDF backend expands these to bitmaps. Visually correct, but text inside
loses selectability and file size increases. Acceptable for small decorative
elements; avoid on large areas or text-heavy containers.

- box-shadow → rasterizes the element; prefer border/outline for large elements
- filter (blur, drop-shadow, brightness, etc.) → rasterized
- SVG filters (feGaussianBlur, etc.) → rasterized

## Work natively - safe to use

- opacity (any value, any size) → native PDF graphics state
- CSS gradients (solid color stops only, no alpha) → native PDF shading objects
- SVG gradients with stop-opacity → native; Skia handles opacity in SVG paint
  correctly, unlike CSS alpha functions. Use `stop-color="currentColor"` with
  `color: var(--bg)` on the SVG element so the resolved hex reaches Skia.
- clip-path (basic shapes) → native
- transform: scale() → works with `contain: size` on the container

## Semi-transparent colors in album components

Skia's PDF backend breaks ALL CSS-level alpha in gradients (color-mix, relative
color syntax, rgb(var(--XX-rgb) / alpha)). Two PDF-safe alternatives:

### SVG stop-opacity (for gradients)

Inline SVG with `stop-opacity` attributes. Skia handles SVG paint opacity
natively. Use `currentColor` to inherit the theme color via CSS `color`:

```html
<svg style="color: var(--bg)" ...>
  <linearGradient id="fade">
    <stop stop-color="currentColor" stop-opacity="1" />
    <stop stop-color="currentColor" stop-opacity="0" />
  </linearGradient>
  <rect fill="url(#fade)" />
</svg>
```

See ElevationProfile.vue and HikeMapPage.vue for real examples.

### CSS opacity on a background element (for solid semi-transparent fills)

When you need a semi-transparent solid background (not a gradient), use a
separate element with `background: var(--bg)` and `opacity: 0.8` behind
the content. CSS `opacity` is native PDF graphics state and works correctly.

```html
<div class="container">
  <div class="bg-layer" />  <!-- opacity: 0.8; background: var(--bg) -->
  <div class="content">...</div>
</div>
```

### Hardcoded rgba()

`rgba(0,0,0,0.5)` works for theme-independent colors (black/white overlays).
Only use when the color is constant across themes.

## Prerequisites (required for all of the above)

- `print-color-adjust: exact` on elements with background colors/images/gradients
- `printBackground: true` in Playwright `page.pdf()` options
- Disable animations: `@media print { * { animation: none !important; transition: none !important; } }`

## WebGL / Mapbox GL maps

Canvas content from WebGL is blank in headless PDF by default. Our pipeline
captures map tiles via CDP and composites them as static images before print.
Any new map rendering must go through this pipeline - never rely on live WebGL
canvas for PDF output.

Test PDF output after any visual changes to album components.
