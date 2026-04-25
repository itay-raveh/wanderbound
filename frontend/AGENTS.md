# Frontend

## Non-Obvious Constraints

- `src/client/` is generated from `../backend/openapi.json` by `openapi-ts`.
  Do not edit it.
- `dev`, `build`, `test`, and `lint` regenerate stale generated assets through
  frontend `ensure:*` scripts, so manual regeneration is rarely needed.
- `lint:frontend` runs `vue-tsc -b` plus eslint. Lint failures may be type
  failures.
- `useWindowVirtualizer` is a custom replacement for @tanstack/vue-virtual due
  to a Vue computed dedup issue.
- `markRaw()` on immutable query responses prevents expensive Vue deep-proxying.
  Do not remove it casually.
- `stripPhotos()` atomically removes photos from all page lists to prevent
  duplicates during drag-and-drop.
- `useTextLayout()` resolves zone geometry from `:root` CSS vars via
  `getComputedStyle`, not DOM containers.
- Quasar q-select `#option` slots need `v-bind="itemProps"` for click handling.

## CSS

- Use rem, never px, except 1px for hairline borders, outlines, and optical nudges. Photo gaps use mm units for print accuracy.
- Use semantic CSS var names (--bg, --text, --surface), never --album-* prefix.
- Use --q-primary for UI accent color. Local per-item variables like country
  color accents are allowed when semantically scoped.
- Design tokens are in App.vue `:root`. Dark/light mode key: `"album-dark-mode"` in localStorage.
- Type scale: `--type-xs` (0.75rem) is the smallest UI size. `--type-3xs` (0.5625rem) is print-only (album pages at A4 scale).
- RTL flipping: use the `rtl-flip` class (in `quasar-overrides.scss`), not custom `[dir="rtl"]` rules.

## Do NOT

- Use ad-hoc UI accent variables instead of --q-primary
- Use default exports
