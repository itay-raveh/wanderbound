# Testing Philosophy: The Testing Trophy

"Write tests. Not too many. Mostly integration."

A test should break only when behavior breaks. Tests verify outcomes at boundaries, not internal wiring.

## Layers

1. **Static analysis** (ruff, ty, ESLint, TypeScript) — catches typos, type errors, dead code.

2. **Unit tests** — pure functions with complex logic, no I/O:
   - Backend: geo math, color algorithms, GPS noise removal, segment classification, boundary splitting, layout calculations
   - Frontend: composables with pure logic (useUndoStack, useTextLayout, useDragState)
   - Fast, deterministic, synthetic data only

3. **Integration tests** (the bulk) — test behavior through real boundaries:
   - Backend: FastAPI `AsyncClient` + in-memory SQLite with transaction rollback. Mock only external services (Mapbox, OpenMeteo, Playwright)
   - Frontend: Vitest + MSW. Composables that interact with API, Pinia Colada query/mutation flows, component rendering with mocked network

4. **E2E tests** (few, high-value) — test what users actually do:
   - Mocked API, Playwright: navigation, routing, auth flows — every commit

## What NOT to test

- Library behavior (Pydantic validation, SQLModel ORM, Vue reactivity primitives)
- Implementation details (internal data structures, private function call order)
- Things static analysis already catches

## Regression Tests

After every bugfix, write a test that reproduces the original bug.
The test must fail without the fix and pass with it. No exceptions.

## Test Data

- **Unit tests**: synthetic data only. Factory functions build exactly what each test needs.
- **Integration tests**: JSON fixtures from `fixtures/trips/` for real-world regression. Synthetic data for everything else.
- **E2E tests**: shared mock objects from `frontend/tests/fixtures/mocks.ts`.

## Scope

Run only the tests relevant to the change:
- Python changes → `mise run test:backend`
- Vue/TS changes → `mise run test:frontend`
- API contract or cross-cutting changes → `mise run test:e2e`

## Backend (pytest)

- **File naming**: `test_{module}.py` mirrors the source module it tests.
- **Test classes**: `TestVerb` or `TestFeature` (e.g., `TestBoundarySplit`).
- **Test methods**: `test_condition_produces_outcome` (e.g., `test_flight_segment_rejected`).
- Factory helpers live in `tests/factories.py`. Fixtures live in `conftest.py`.
- pytest-asyncio auto mode. pytest-randomly for ordering.
- syrupy for snapshot testing complex outputs (segment pipeline, layout builder, API shapes).
- pytest-httpx for mocking external HTTP (Mapbox, OpenMeteo).

## Frontend (Vitest)

- Environment: happy-dom (vitest.config.ts)
- Mock APIs with MSW handlers (tests/mocks/)
- Mount components with @vue/test-utils
- Shared mock data in `tests/fixtures/mocks.ts`

## E2E (Playwright)

- Tests live in `e2e/`, mocked API, runs every commit
- Shared mock data imported from `tests/fixtures/mocks.ts`
