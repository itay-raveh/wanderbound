# Testing Philosophy

"Write tests. Not too many. Mostly integration."

Every test must earn its place. Prefer confidence per test over coverage
percentage.

## Layer Choice

- Unit tests are for pure computation, edge-heavy transformations, parsing,
  formatting, and payload builders.
- Integration tests are the default for API and data-flow boundaries.
- E2E tests are for user interaction, async timing, DOM behavior, scrolling,
  keyboard handling, and multi-system flows.

Avoid tests that only prove wiring, initial state, library behavior, or mock
behavior. If a test needs more mocks than assertions, it is probably at the
wrong layer.

## Conventions

- Frontend integration: Vitest + MSW. Do not mock Vue internals.
- Backend integration: FastAPI `AsyncClient` with in-memory async SQLite and
  transaction rollback.
- E2E: Playwright route handlers for mocked API. Assert user-observable behavior,
  not implementation details.
- Snapshot tests are only for serialized contract boundaries. Never snapshot DOM.

After bugfixes, write a regression test that fails without the fix and passes
with it. Choose the layer that would have caught the original bug.

Run scoped tests:

- Python changes: `mise run test:backend`
- Vue/TS changes: `mise run test:frontend`
- API contract or cross-cutting changes: `mise run test:e2e`
