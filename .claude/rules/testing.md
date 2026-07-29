# Testing Philosophy

"Write tests. Not too many. Mostly integration."

Tests are permanent production code with a maintenance cost. Add one only when
it is the cheapest reliable way to detect a specific, high-impact regression.
Coverage percentage, implementation complexity, and the existence of a code
path are not reasons to add tests.

## Admission Rule

A test must protect at least one of these risks:

- authorization, authentication, or another security boundary;
- data loss, corruption, cross-user leakage, or transaction atomicity;
- an external API, file-format, migration, or other compatibility contract;
- an edge-heavy domain algorithm where examples clarify required behavior;
- concurrency, cancellation, retry, or recovery behavior that has failed or is
  inherently race-prone;
- browser behavior that cannot be tested below E2E, such as focus, scrolling,
  file pickers, popups, or rendering and print integration;
- a regression for a real defect whose recurrence would have meaningful user
  impact.

If a test does not clearly fit one of these categories, do not add it. If two
tests protect the same risk, keep the cheaper and more direct one. New tests
should replace overlapping coverage instead of accumulating another layer.

Delete tests when their protected behavior moves to a stronger retained test,
when the implementation they describe disappears, or when they only make a
refactor harder without detecting a user-visible regression.

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

Do not test wiring, initial state, static rendering, library behavior, generated
client behavior, model-library parsing, logs, metrics, internal defaults,
private call sequences, or mocks. Do not add a CRUD happy-path test unless it
crosses a security, transaction, or compatibility boundary. If a test needs
more mocks than assertions, delete it or move the assertion to a real boundary.

Do not assert exact internal tuning defaults such as concurrency, timeout,
retry, batch-size, or cache-capacity values. Inject configuration when needed
to exercise behavior. Exact assertions remain appropriate for external
contracts and user-visible requirements.

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

After a bugfix, add a regression test only when the admission rule is satisfied.
It must fail without the fix, and it belongs at the lowest layer that reproduces
the actual failure. A bugfix does not automatically justify a permanent test.

During review, require the author to name the unique regression each new test
detects and why an existing retained test cannot detect it. Remove the test if
that answer is vague.

Run scoped tests:

- Python changes: `mise run test:backend`
- Vue/TS changes: `mise run test:frontend`
- API contract or cross-cutting changes: `mise run test:e2e`
