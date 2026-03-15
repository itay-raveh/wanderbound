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

## File Naming
- Components: PascalCase (`UserCard.vue`)
- Composables: camelCase with `use` prefix (`useAuth.ts`)
- Stores: camelCase with `Store` suffix in Pinia (`useUserStore`)
- Views: PascalCase matching route name (`Dashboard.vue`)

## Anti-Patterns
- God components (150+ lines mixing layout, logic, fetching, and state)
- Prop drilling through 3+ levels — use Pinia or provide/inject
- Manual DOM manipulation — use Vue refs and reactivity
- Event buses or custom pub/sub — use Pinia stores
- Duplicating validation or business logic that the backend already enforces
- Per-component error handling that should be centralized
- `watch` used to imperatively sync state — use `computed` instead
- Fetching the same data in multiple components — lift to a shared store or composable
