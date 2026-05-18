# Testing Philosophy

"Write tests. Not too many. Mostly integration."

Every test must earn its place. Prefer confidence per test over coverage
percentage.

## Layer Choice

- Unit tests are for pure computation, edge-heavy transformations, parsing,
  formatting, payload builders, layout math, and small deterministic helpers.
- Backend integration tests are the default for API, database, filesystem,
  transaction, and data-flow boundaries.
- Frontend integration tests are for composables, Pinia Colada cache behavior,
  component interactions, and API hooks with MSW.
- E2E tests are for user interaction, async timing, DOM focus, scrolling,
  keyboard handling, file picker or popup behavior, and multi-component
  workflows that cannot be covered cheaply below.

Avoid tests that only prove wiring, initial state, library behavior, generated
client behavior, mock behavior, or log output. If a test needs more mocks than
assertions, it is probably at the wrong layer.

## Conventions

- Frontend integration: Vitest + MSW. Do not mock Vue internals.
- Backend integration: FastAPI `AsyncClient` with in-memory async SQLite and
  transaction rollback.
- E2E: Playwright route handlers for mocked API. Assert user-observable behavior,
  not implementation details.
- Snapshot tests are only for serialized contract boundaries. Never snapshot DOM.

## Helper Libraries

Use plain fixtures and typed builders first.

- Do not add `factory_boy`, `pytest-factoryboy`, `polyfactory`, or `Faker`
  unless model creation remains noisy after local builders are split.
- Do not add `@pinia/testing` unless a store-heavy component test needs action
  stubbing that the current Pinia setup cannot express cleanly.
- Do not add Testing Library or `user-event` unless Vue Test Utils tests keep
  asserting implementation details that Playwright cannot cover more cheaply.

## Structure

- Keep shared setup in `support/` modules or focused fixtures.
- Let fixtures do setup and teardown. Use plain builder functions for data.
- Prefer one state-changing action per helper.
- Move repeated E2E route stubs into Playwright support files.
- Move files into `unit/` and `integration/` directories only after helper
  boundaries are stable enough to avoid churn.

After bugfixes, write a regression test that fails without the fix and passes
with it. Choose the layer that would have caught the original bug.

Run scoped tests:

- Python changes: `mise run test:backend`
- Vue/TS changes: `mise run test:frontend`
- API contract or cross-cutting changes: `mise run test:e2e`
