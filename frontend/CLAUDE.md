# Frontend (Vue)

## Commands
- `npm run dev` — start dev server
- `npm run build` — production build
- `npm run lint` — lint check

## Architecture

**Component design:** Each component should do one thing. If a component handles layout, data fetching, state management, and business logic, it's a god component — split it. Views (route-level components) orchestrate; child components render. Composables hold shared logic. Pinia stores hold shared state.

**State ownership:** State should live in exactly one place. Local `ref()` for component-only state. Pinia store for state shared across components or that persists across navigation. Derive everything else with `computed`. If you find yourself syncing state between two places, the state is in the wrong place.

**API layer:** One thin API client — not a wrapper function per endpoint. Components never call `fetch` directly; they use composables that call the API client. The API client handles auth headers, base URL, and error handling in one place.

**Types:** TypeScript strict mode, no `any`. Backend response types should be defined once and used consistently. If the backend schema changes, the frontend types change in one place.

## Conventions
- Composition API with `<script setup>` exclusively — never Options API
- Pinia for shared state — one store per domain concept
- Composables (`src/composables/use*.ts`) for reusable logic
- Vue Router for all navigation — no manual `window.location`
- `computed` for derived state — never `watch` to sync one ref into another
- Handle loading/error/empty states consistently — use a shared composable or pattern, not ad-hoc per component
- Use `v-model` and built-in directives — don't reimplement two-way binding
- Colocate components with their route when possible
- Derive frontend state from the backend wherever possible — don't maintain parallel data models that duplicate what the API already provides
- Prefer native HTML elements and CSS over heavy component libraries — unless the project has already committed to one

## File Naming
- Components: PascalCase (`UserCard.vue`)
- Composables: camelCase with `use` prefix (`useAuth.ts`)
- Stores: camelCase with `Store` suffix in Pinia (`useUserStore`)
- Views: PascalCase matching route name (`Dashboard.vue`)

## Design System

The app has two styling contexts: **editor chrome** (sidebar, header, menus, registration) and **album pages** (A4 print-ready pages rendered in the viewer). They share a token system but follow different rules.

### Layers

| Layer | File | Resolves at | What it controls |
|-------|------|-------------|-----------------|
| Quasar SASS variables | `src/quasar-variables.sass` | Build time | Typography maps (`$h5`, `$body2`, etc.), `$text-weights`, `$generic-border-radius`, component defaults |
| CSS custom properties | `App.vue` global `<style>` | Runtime | Dark/light colors, radius scale, page typography, spacing, transitions |
| Global Quasar overrides | `src/styles/quasar-overrides.scss` | Runtime | Form field theming, QMenu styling (needs CSS vars, can't be SASS) |

### Editor chrome — use Quasar utility classes

For layout, typography, and spacing in editor chrome components, prefer Quasar classes over custom CSS:

- **Flex layout:** `.row`, `.column`, `.flex` + alignment (`.items-center`, `.justify-between`, etc.)
- **Typography:** `.text-body2`, `.text-caption`, `.text-overline`, `.text-h5`, `.text-h6`, `.text-subtitle1`, `.text-subtitle2`
- **Weights:** `.text-weight-bold`, `.text-weight-semibold`, `.text-weight-medium` (extended via `$text-weights` in SASS)
- **Text:** `.text-uppercase`, `.text-italic`, `.text-center`, `.text-justify`
- **Spacing:** `.q-pa-sm`, `.q-ml-auto`, `.q-gutter-x-sm`, `.q-gutter-y-sm`, etc.
- **Positioning:** `.relative-position`, `.absolute-full`, `.overflow-hidden`, `.fit`
- **Interaction:** `.cursor-pointer`, `.non-selectable`, `.no-pointer-events`
- **Color:** `.text-primary`, `.text-negative`, `.bg-primary` (Quasar built-in) + `.text-bright`, `.text-muted`, `.text-faint`, `.text-danger`, `.bg-danger` (custom palette in `App.vue`, follows [Quasar convention](https://quasar.dev/style/color-palette#adding-your-own-colors) with `!important`)
- **Shadow:** `.shadow-1` through `.shadow-5` (auto-switch in dark mode)

**Critical gotchas:**
- `.row`, `.column`, `.flex` ALL set `flex-wrap: wrap`. Always add `.no-wrap` unless wrapping is explicitly desired.
- `all: unset` in scoped CSS has higher specificity than Quasar global classes (due to Vue's `[data-v-xxx]`). On elements with `all: unset`, do NOT use Quasar flex classes — write `display: flex; align-items: center;` in CSS instead.

### Album pages — use CSS custom properties

Album pages have specific typographic design for A4 print. Use the token scale from `App.vue`:

- **Font sizes:** `--display-1` (3.75rem), `--display-2` (3rem), `--type-xl` through `--type-3xs`
- **Radius:** `--radius-xs` (2px) through `--radius-full` (999px)
- **Tracking:** `--tracking-tight` (-0.02em), `--tracking-wide` (0.06em), `--tracking-wider` (0.2em)
- **Page spacing:** `--page-inset-x` (3rem), `--page-inset-y` (2.5rem), `--gap-lg` (1rem), `--gap-md-lg` (0.75rem), `--gap-md` (0.5rem), `--gap-sm-md` (0.375rem), `--gap-sm` (0.25rem), `--gap-xs` (0.125rem)
- **Step layout:** `--meta-ratio` (0.42) — meta panel fraction of page width, used in step components and `useTextMeasure.ts`
- **Photo grids:** `--photo-gap-lg` (5mm) through `--photo-gap-xs` (2mm)
- **Map pages:** `--page-dark-surface`, `--page-dark-overlay`
- **Timing:** `--duration-fast` (0.15s), `--duration-normal` (0.3s), `--duration-slow` (0.5s)

Font weights in album pages stay as literal values (`font-weight: 600`) — no token needed since they don't vary by theme.

### Theme colors

Dark/light mode colors are CSS custom properties on `.body--dark` / `.body--light` in `App.vue`: `--bg`, `--bg-secondary`, `--bg-deep`, `--text`, `--text-bright`, `--text-muted`, `--text-faint`, `--surface`, `--border-color`, `--danger`. Quasar brand color `--q-primary` is set in `main.ts`.

### Stat colors

Centralized in `src/components/album/colors.ts` as `STAT_COLORS` — used by overview page components. Add new stat colors there, not as inline hex values.

## Anti-Patterns
- God components (150+ lines mixing layout, logic, fetching, and state)
- Prop drilling through 3+ levels — use Pinia or provide/inject
- Manual DOM manipulation — use Vue refs and reactivity
- Event buses or custom pub/sub — use Pinia stores
- Duplicating validation or business logic that the backend already enforces
- Per-component error handling that should be centralized
- `watch` used to imperatively sync state — use `computed` instead
- Fetching the same data in multiple components — lift to a shared store or composable
