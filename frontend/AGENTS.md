# Frontend

Vue components own presentation, composables own reusable stateful behavior,
and query modules own Pinia Colada server state.

## Constraints

- `src/client/` is generated from `../backend/openapi.json`. Do not edit it.
- Frontend `dev`, `build`, `test`, and `lint` commands run the relevant
  `ensure:*` generation steps automatically.
- `mise run lint:frontend` runs type checking and ESLint, so lint failures may
  be TypeScript failures.
- `useWindowVirtualizer` works around Vue reactivity problems in the upstream
  TanStack adapter. Keep the local adapter until its documented upstream issue
  is resolved.
- Photo moves must update every page and the unused list atomically. Use the
  helpers in `useStepLayout.ts` rather than mutating one list independently.
- `useTextLayout()` derives print geometry from root CSS tokens. Do not replace
  that geometry with measurements from scaled preview elements.
- Quasar `q-select` option slots must bind `itemProps` for interaction.

## CSS

- Design tokens live in `App.vue`. Reuse them instead of copying their values.
- Use rem for UI dimensions. Use mm for album geometry and photo gaps. One-pixel
  hairlines and intentional optical nudges are allowed.
- Use `--q-primary` for the application accent and semantic local variables for
  domain-specific colors.
- Use logical properties and the shared `rtl-flip` class for directional icons.
