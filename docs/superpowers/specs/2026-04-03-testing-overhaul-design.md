# Testing Overhaul Design

## Goals

- Tests are easy to maintain and clear in intention
- Tests protect against bugs, not against code changes
- Tests don't break on internal implementation changes
- Test data is reproducible, CI-friendly, and shared with the future demo feature
- Manual verification is reduced to what genuinely can't be automated

## Testing Philosophy: The Testing Trophy

"Write tests. Not too many. Mostly integration."

A test should break only when behavior breaks. Tests verify outcomes at boundaries, not internal wiring.

### Layers

1. **Static analysis** (ruff, ty, ESLint, TypeScript) — catches typos, type errors, dead code. Already in place, no changes needed.

2. **Unit tests** — pure functions with complex logic, no I/O:
   - Backend: geo math, color algorithms, GPS noise removal, segment classification, boundary splitting, layout calculations
   - Frontend: composables with pure logic (useUndoStack, useTextLayout, useDragState)
   - Fast, deterministic, synthetic data only

3. **Integration tests** (the bulk) — test behavior through real boundaries:
   - Backend: FastAPI `AsyncClient` + in-memory SQLite with transaction rollback. Mock only external services (Mapbox, OpenMeteo, Playwright)
   - Frontend: Vitest + MSW. Composables that interact with API, Pinia Colada query/mutation flows, component rendering with mocked network

4. **E2E tests** (few, high-value) — test what users actually do:
   - Fast suite (mocked API): navigation, routing, auth flows — every commit
   - Full suite (real backend): drag-drop, photo focus, scroll, undo/redo — pre-merge/nightly

### What NOT to test

- Library behavior (Pydantic validation, SQLModel ORM, Vue reactivity primitives)
- Implementation details (internal data structures, private function call order)
- Things static analysis already catches

## Test Data Architecture

Two datasets, one shared foundation.

### Dataset 1: Demo Trip (photos + metadata)

- **Purpose**: Future "Try demo" landing page button AND E2E tests with real backend
- **Source**: Curated subset of the South America trip — 5-8 steps, ~30 hand-picked landscape/animal photos (no people)
- **Contents**: `trip.json`, `locations.json`, step folders with photos, no videos
- **Storage**: Git LFS for photo binaries, regular git for JSON
- **Location**: `fixtures/demo/`
- **Size target**: 20-50MB

### Dataset 2: Full Trip JSONs (metadata only)

- **Purpose**: Backend integration/regression tests — segmentation pipeline, step processing, GPS edge cases
- **Source**: Existing `trip.json` + `locations.json` for South America and Naples trips
- **Contents**: JSON only, zero binary files
- **Storage**: Regular git
- **Location**: `fixtures/trips/`

### Unit test data: synthetic only

- Factory functions build exactly the data each test needs
- Existing helpers: `_track()`, `_pt()`, `_step()`, `create_test_jpeg()`, `make_points()`
- Factory helpers in conftest: `insert_album()`, `insert_step()`, `insert_segment()`, `sign_in_and_upload()`

### Deleted

- `backend/tests/test_data/` (4.7GB) — replaced by the two datasets above
- Duplicated mock data in `frontend/tests/mocks/handlers.ts` and `frontend/e2e/fixtures.ts` — unified into `frontend/tests/fixtures/mocks.ts`

## Test Infrastructure

### Backend (pytest)

**Kept as-is:**
- pytest-asyncio (async support)
- pytest-randomly (catch order-dependent tests)
- In-memory SQLite with transaction rollback
- `AsyncClient` with `ASGITransport`
- `mock_jwt()` for auth bypass

**Changed:**
- Factory helpers (`insert_album`, `insert_step`, `insert_segment`, `sign_in_and_upload`) move from `conftest.py` to `factories.py` — conftest keeps only fixtures
- `sa_trip_dir` / `sa_trip` / `sa_locations` fixtures repointed to `fixtures/trips/` instead of `backend/tests/test_data/`

**Added:**
- **syrupy** — snapshot testing for segment pipeline output, layout builder results, API response shapes. Avoids brittle field-by-field assertions for complex outputs.
- **pytest-httpx** — mock external HTTP calls (Mapbox, OpenMeteo) via request/response recording instead of manual `patch()`. Asserts expected calls were made.

**Not added:**
- polyfactory/factory_boy — models are simple enough for plain factory functions
- pytest-cov in test runner — coverage is a CI reporting concern

### Frontend (Vitest)

**Kept as-is:**
- happy-dom environment
- MSW for API mocking
- @vue/test-utils for component mounting
- Global Quasar plugin setup

**Changed:**
- Shared mock data (user, album, steps, segments, media) extracted to `frontend/tests/fixtures/mocks.ts` — single source for Vitest MSW handlers and Playwright E2E fixtures
- mapbox-gl mock moves from `setup.ts` to `__mocks__/mapbox-gl.ts` (Vitest auto-mock convention)

### E2E (Playwright)

**Kept as-is:**
- Custom `authedPage` fixture via `test.extend`

**Changed:**
- Mock data imported from shared `frontend/tests/fixtures/mocks.ts`
- `webServer` config added to `playwright.config.ts` for full-backend suite
- New fixtures: DB seeding via API, authenticated session with real JWT

**New interaction tests:**
- Drag-drop photo reorder
- Photo focus/unfocus
- Scroll-to-step
- Undo/redo
- Segment boundary drag

**Structure:**
```
frontend/e2e/
  fast/              # mocked API, every commit
    smoke.test.ts
    navigation.test.ts
  full/              # real backend, pre-merge
    editor-interactions.test.ts
    photo-management.test.ts
```

## Test File Structure

### Backend

Flat `tests/` with `test_{module}.py` mirroring source — no change to structure.

**Naming:**
- Classes: `TestVerb` or `TestFeature` (e.g., `TestBoundarySplit`)
- Methods: `test_condition_produces_outcome` (e.g., `test_flight_segment_rejected`)

**Fixes to existing tests:**
- `test_pipeline.py`: use shared `session` fixture + `insert_*` helpers instead of creating its own engine
- `test_segments.py`: integration tests load from `fixtures/trips/` instead of 4.7GB test_data
- Remove local `make_points()` duplicates — import from factories

### Frontend

Tests organized by type (`components/`, `composables/`, `mutations/`, `queries/`, `logic/`, `utils/`) — no change to structure.

**Fixes:**
- Delete shallow "renders without error" tests that don't verify behavior
- Extract mock data to shared `frontend/tests/fixtures/mocks.ts`

### Shared Fixtures Directory

```
fixtures/
  demo/                          # Demo trip (Git LFS for photos)
    trip.json
    locations.json
    step-1_name/
      photos/
        landscape1.jpg           # LFS-tracked
        landscape2.jpg
    step-2_name/
      photos/
        ...
  trips/                         # Full trip JSONs (no media)
    south-america-2024-2025/
      trip.json
      locations.json
    naples-sorrento-2022/
      trip.json
      locations.json
frontend/tests/fixtures/
  mocks.ts                       # Shared mock data for Vitest + E2E (imported by both)
```
