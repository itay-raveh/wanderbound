# Testing Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul test data, infrastructure, and conventions so tests are maintainable, behavior-focused, CI-ready, and share data with the future demo feature.

**Architecture:** Two test data tiers (demo trip with photos via Git LFS, full trip JSONs for regression), backend refactored to use factories + syrupy snapshots + pytest-httpx, frontend unified mock data, E2E split into fast (mocked) and full (real backend) suites.

**Tech Stack:** pytest, syrupy, pytest-httpx, Vitest, MSW, Playwright, Git LFS

**Spec:** `docs/superpowers/specs/2026-04-03-testing-overhaul-design.md`

---

### Task 1: Document Testing Philosophy

Write the testing philosophy to `.claude/rules/testing.md`, replacing its current content. This is the canonical reference for all future test decisions.

**Files:**
- Modify: `.claude/rules/testing.md`

- [ ] **Step 1: Write the testing philosophy document**

```markdown
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
   - Fast suite (mocked API): navigation, routing, auth flows — every commit
   - Full suite (real backend): drag-drop, photo focus, scroll, undo/redo — pre-merge/nightly

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
- **E2E tests (full)**: demo trip from `fixtures/demo/` seeded via API.
- **E2E tests (fast)**: shared mock objects from `frontend/tests/fixtures/mocks.ts`.

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

- `e2e/fast/` — mocked API, runs every commit
- `e2e/full/` — real backend, runs pre-merge/nightly
- Shared mock data imported from `tests/fixtures/mocks.ts`
```

- [ ] **Step 2: Commit**

```bash
git add .claude/rules/testing.md
git commit -m "docs: replace testing conventions with Testing Trophy philosophy"
```

---

### Task 2: Set Up Fixtures Directory and Migrate Trip JSONs

Move the trip JSON files from the untracked `backend/tests/test_data/` to a tracked `fixtures/trips/` directory. No photos — JSON only.

**Files:**
- Create: `fixtures/trips/south-america-2024-2025/trip.json` (copy from `backend/tests/test_data/trip/south-america-2024-2025_14232450/trip.json`)
- Create: `fixtures/trips/south-america-2024-2025/locations.json` (copy from `backend/tests/test_data/trip/south-america-2024-2025_14232450/locations.json`)
- Create: `fixtures/trips/naples-sorrento-2022/trip.json` (copy from `backend/tests/test_data/trip/naples-sorrento-2022_14455378/trip.json`)
- Create: `fixtures/trips/naples-sorrento-2022/locations.json` (copy from `backend/tests/test_data/trip/naples-sorrento-2022_14455378/locations.json`)

- [ ] **Step 1: Create fixtures directory and copy JSONs**

```bash
mkdir -p fixtures/trips/south-america-2024-2025
mkdir -p fixtures/trips/naples-sorrento-2022

cp backend/tests/test_data/trip/south-america-2024-2025_14232450/trip.json fixtures/trips/south-america-2024-2025/
cp backend/tests/test_data/trip/south-america-2024-2025_14232450/locations.json fixtures/trips/south-america-2024-2025/
cp backend/tests/test_data/trip/naples-sorrento-2022_14455378/trip.json fixtures/trips/naples-sorrento-2022/
cp backend/tests/test_data/trip/naples-sorrento-2022_14455378/locations.json fixtures/trips/naples-sorrento-2022/
```

- [ ] **Step 2: Verify JSONs are valid**

```bash
python3 -c "import json, pathlib; [json.loads(p.read_text()) for p in pathlib.Path('fixtures/trips').rglob('*.json')]; print('All valid')"
```

Expected: `All valid`

- [ ] **Step 3: Commit**

```bash
git add fixtures/trips/
git commit -m "chore: add trip JSON fixtures for backend regression tests"
```

---

### Task 3: Set Up Git LFS and Demo Trip Scaffold

Install Git LFS, configure it for the `fixtures/demo/` directory, and create the directory structure. The actual photo curation is a manual step — this task sets up the infrastructure.

**Files:**
- Create: `.gitattributes` (LFS tracking for demo photos)
- Create: `fixtures/demo/.gitkeep`

- [ ] **Step 1: Install Git LFS**

```bash
sudo apt-get install git-lfs
git lfs install
```

- [ ] **Step 2: Configure LFS tracking for demo photos**

Add to `.gitattributes` (create if it doesn't exist):

```
fixtures/demo/**/*.jpg filter=lfs diff=lfs merge=lfs -text
fixtures/demo/**/*.jpeg filter=lfs diff=lfs merge=lfs -text
fixtures/demo/**/*.png filter=lfs diff=lfs merge=lfs -text
fixtures/demo/**/*.webp filter=lfs diff=lfs merge=lfs -text
```

- [ ] **Step 3: Create demo directory scaffold**

```bash
mkdir -p fixtures/demo
touch fixtures/demo/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add .gitattributes fixtures/demo/
git commit -m "chore: set up Git LFS for demo trip photos"
```

> **Note:** Curating the actual demo trip (selecting 5-8 steps, picking ~30 landscape photos, creating trip.json/locations.json subset) is a separate manual task. This task only sets up the infrastructure.

---

### Task 4: Add Backend Test Dependencies

Add syrupy and pytest-httpx to the dev dependency group.

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add dependencies**

In `backend/pyproject.toml`, add to the `[dependency-groups] dev` list:

```
    "syrupy~=4.0",
    "pytest-httpx~=0.35",
```

- [ ] **Step 2: Install**

```bash
cd backend && uv sync
```

- [ ] **Step 3: Verify imports work**

```bash
cd backend && uv run python -c "import syrupy; import pytest_httpx; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore: add syrupy and pytest-httpx dev dependencies"
```

---

### Task 5: Extract Factory Helpers from conftest.py

Move factory functions out of `conftest.py` into `factories.py`. Conftest should only have fixtures and fixture-like things.

**Files:**
- Create: `backend/tests/factories.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_albums.py` (update imports)
- Modify: `backend/tests/test_auth.py` (update imports)
- Modify: `backend/tests/test_builder.py` (update imports)
- Modify: `backend/tests/test_media.py` (update imports)
- Modify: any other test files importing from conftest

- [ ] **Step 1: Identify all factory functions in conftest.py**

These functions are factories/helpers, NOT fixtures (no `@pytest.fixture` decorator):
- `collect_async()` (line 31)
- `create_test_jpeg()` (line 35)
- `make_async_session_mock()` (line 51)
- `mock_jwt()` (line 127)
- `mock_extract()` (line 151)
- `sign_in_and_upload()` (line 162)
- `make_points()` (line 185)
- `insert_album()` (line 192)
- `insert_step()` (line 216)
- `insert_segment()` (line 243)

These constants are used by the factories:
- `TEST_DATA_DIR` (line 58)
- `GOOGLE_PAYLOAD`, `MICROSOFT_PAYLOAD`, `_DEFAULT_PAYLOADS` (lines 101-114)
- `PS_USER`, `TRIPS` (lines 116-124)
- `LOCATION`, `WEATHER`, `AID` (lines 178-183)

- [ ] **Step 2: Create `backend/tests/factories.py`**

Move ALL functions and constants listed above into `factories.py`. Keep the same imports they need. Update `TEST_DATA_DIR` to point to the new `fixtures/trips/` location:

```python
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
TRIPS_DIR = FIXTURES_DIR / "trips"
```

- [ ] **Step 3: Update conftest.py**

Remove the moved functions/constants. Import them from `factories` for the fixtures that use them. The fixtures that remain in conftest are:
- `engine` (session-scoped)
- `session`
- `client`
- `sa_trip_dir` — update to use `TRIPS_DIR / "south-america-2024-2025"`
- `sa_trip`
- `sa_locations`

Update the `sa_trip_dir` fixture:

```python
from .factories import TRIPS_DIR

@pytest.fixture(scope="module")
def sa_trip_dir() -> Path:
    trip_dir = TRIPS_DIR / "south-america-2024-2025"
    assert trip_dir.exists(), f"SA trip fixtures not found at {trip_dir}"
    return trip_dir
```

- [ ] **Step 4: Update all test file imports**

Search for every file that imports from `.conftest` and update to import from `.factories` instead. Key files:
- `test_albums.py`: imports `AID, insert_album, insert_segment, insert_step, make_points, sign_in_and_upload`
- `test_auth.py`: imports `GOOGLE_PAYLOAD, MICROSOFT_PAYLOAD, PS_USER, mock_extract, mock_jwt, sign_in_and_upload`
- `test_builder.py`: imports `collect_async, create_test_jpeg`
- `test_media.py`: imports `create_test_jpeg`
- `test_deps.py`: imports `make_async_session_mock`
- Check all other test files for conftest imports.

- [ ] **Step 5: Run tests to verify nothing broke**

```bash
cd backend && uv run pytest -x -q
```

Expected: all tests pass (except integration tests that depend on the old `test_data/` path — those are fixed in Task 6).

- [ ] **Step 6: Commit**

```bash
git add backend/tests/factories.py backend/tests/conftest.py backend/tests/test_*.py
git commit -m "refactor: extract factory helpers from conftest to factories.py"
```

---

### Task 6: Migrate test_segments.py Integration Tests to fixtures/trips/

The integration tests in `test_segments.py` use `sa_trip` and `sa_locations` fixtures that previously pointed to `backend/tests/test_data/`. After Task 5, they point to `fixtures/trips/`. Verify they work.

**Files:**
- Modify: `backend/tests/test_segments.py` (only if path adjustments needed)

- [ ] **Step 1: Run the segment integration tests**

```bash
cd backend && uv run pytest tests/test_segments.py -x -v -k "Integration or KnownHikes or FullTrip or MultiDayHikeRangesIntegration"
```

Expected: All pass — the `sa_trip_dir` fixture was already updated in Task 5 to point to `fixtures/trips/south-america-2024-2025/`.

- [ ] **Step 2: If tests fail, debug path issues**

The `PSTrip.from_trip_dir()` and `PSLocations.from_trip_dir()` methods load `trip.json` and `locations.json` from a directory. Verify the fixture directory structure matches what these methods expect. The old path had a `south-america-2024-2025_14232450` suffix — check if the numeric suffix matters.

If `from_trip_dir()` hardcodes parsing the directory name to extract an ID, the fixture directory may need to be renamed to include the ID: `fixtures/trips/south-america-2024-2025_14232450/`.

- [ ] **Step 3: Commit (if any changes were needed)**

```bash
git add backend/tests/ fixtures/trips/
git commit -m "fix: update segment integration tests to use fixtures/trips/"
```

---

### Task 7: Refactor test_pipeline.py to Use Shared Fixtures

`test_pipeline.py` creates its own SQLite engine, manually constructs all model instances, and patches `get_engine`. It should use the shared `session` fixture and factory helpers.

**Files:**
- Modify: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Read the current test**

Read `backend/tests/test_pipeline.py` (163 lines). Understand what `_save_reupload` does and what the test verifies: that reconciled albums have their old segments and steps deleted, and new ones saved.

- [ ] **Step 2: Rewrite using shared fixtures**

The test needs its own engine because `_save_reupload` calls `get_engine()` internally. This is a genuine need — it can't use the shared `session` fixture directly because the function under test creates its own sessions.

Keep the test's own engine, but use factory helpers for constructing model instances instead of raw constructors. Import `LOCATION`, `WEATHER` from `factories` instead of constructing `Weather(day=WeatherData(...))` inline.

Replace the verbose inline model construction with calls to `insert_album()`, `insert_step()`, `insert_segment()` — but note these are async and take a session, which this test manages manually. So the right approach is: keep the manual session management (because `_save_reupload` needs its own engine), but extract the repetitive model construction into local helpers or use the factory constants.

Specifically:
- Import `LOCATION`, `WEATHER`, `AID` from `factories`
- Use the same weather/location patterns as conftest factories
- Remove the duplicated `_make_points()` — import `make_points` from `factories`

- [ ] **Step 3: Run the test**

```bash
cd backend && uv run pytest tests/test_pipeline.py -x -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_pipeline.py
git commit -m "refactor: use shared factory constants in test_pipeline.py"
```

---

### Task 8: Add Syrupy Snapshot Tests for Segment Pipeline

Add snapshot tests for `build_segments()` output using syrupy. This captures the full pipeline output shape so future changes that alter segment structure are caught without maintaining fragile field-by-field assertions.

**Files:**
- Create: `backend/tests/__snapshots__/` (auto-generated by syrupy)
- Modify: `backend/tests/test_segments.py`

- [ ] **Step 1: Write snapshot test for synthetic segments**

Add to `test_segments.py`, in a new class at the end:

```python
class TestSegmentPipelineSnapshot:
    """Snapshot test: captures full build_segments() output shape.

    Run with --snapshot-update to regenerate after intentional changes.
    """

    def test_basic_trip_snapshot(self, snapshot) -> None:
        """A simple trip produces a stable segment list."""
        steps = [
            _step(52.37, 4.89, 8.0),   # Amsterdam morning
            _step(51.44, 5.47, 12.0),   # Eindhoven midday
            _step(50.85, 4.35, 18.0),   # Brussels evening
        ]
        gps = (
            _track(52.37, 4.89, 51.44, 5.47, h0=8.0, h1=11.5, n=30)
            + _track(51.44, 5.47, 50.85, 4.35, h0=12.5, h1=17.5, n=30)
        )
        segments = build_segments(steps, gps)
        # Snapshot the kinds and point counts (not exact coordinates — those are synthetic)
        result = [
            {"kind": s.kind.value, "num_points": len(s.points)}
            for s in segments
        ]
        assert result == snapshot
```

- [ ] **Step 2: Run with --snapshot-update to create initial snapshot**

```bash
cd backend && uv run pytest tests/test_segments.py::TestSegmentPipelineSnapshot -v --snapshot-update
```

Expected: snapshot file created in `tests/__snapshots__/`

- [ ] **Step 3: Run again without --snapshot-update to verify it passes**

```bash
cd backend && uv run pytest tests/test_segments.py::TestSegmentPipelineSnapshot -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_segments.py backend/tests/__snapshots__/
git commit -m "test: add syrupy snapshot test for segment pipeline output"
```

---

### Task 9: Extract Shared Frontend Mock Data

Create `frontend/tests/fixtures/mocks.ts` as the single source of truth for mock data used by both Vitest MSW handlers and Playwright E2E fixtures.

**Files:**
- Create: `frontend/tests/fixtures/mocks.ts`
- Modify: `frontend/tests/mocks/handlers.ts`
- Modify: `frontend/e2e/fixtures.ts`

- [ ] **Step 1: Create the shared mock data file**

```typescript
// frontend/tests/fixtures/mocks.ts
// Single source of truth for test mock data.
// Used by both Vitest MSW handlers and Playwright E2E fixtures.

export const mockUser = {
  id: 1,
  google_sub: "g-1",
  first_name: "Test",
  last_name: "User",
  profile_image_url: null,
  locale: "en-US",
  unit_is_km: true,
  temperature_is_celsius: true,
  album_ids: ["aid-1"],
  has_data: true,
  living_location: null,
};

export const mockAlbum = {
  id: "aid-1",
  uid: 1,
  title: "South America",
  subtitle: "A great adventure",
  excluded_steps: [],
  maps_ranges: [],
  front_cover_photo: "cover.jpg",
  back_cover_photo: "back.jpg",
  colors: { nl: "#e77c31" },
};

export const mockMedia = [
  { name: "cover.jpg", width: 1920, height: 1080 },
  { name: "photo1.jpg", width: 1920, height: 1080 },
  { name: "photo2.jpg", width: 1080, height: 1920 },
];

export const mockStep = {
  id: 1,
  name: "Amsterdam",
  description: "Visited the canals.",
  timestamp: 1704067200,
  timezone_id: "Europe/Amsterdam",
  location: {
    name: "Amsterdam",
    detail: "North Holland",
    country_code: "nl",
    lat: 52.37,
    lon: 4.89,
  },
  elevation: 0,
  weather: {
    day: { temp: 5, feels_like: 2, icon: "cloudy" },
    night: null,
  },
  cover: "photo1.jpg",
  pages: [["photo1.jpg", "photo2.jpg"]],
  unused: [],
  datetime: "2024-01-01T12:00:00+01:00",
};

export const mockSteps = [mockStep];

export const mockSegmentOutlines = [
  {
    start_time: 1704060000,
    end_time: 1704067200,
    kind: "driving",
    timezone_id: "Europe/Amsterdam",
    start_coord: [52.0, 4.0],
    end_coord: [52.37, 4.89],
  },
];

/** 1x1 transparent JPEG as base64 for media route stubs. */
export const TINY_JPEG_BASE64 =
  "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAFBABAAAAAAAAAAAAAAAAAAAACf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AKgA/9k=";
```

- [ ] **Step 2: Update handlers.ts to import from shared mocks**

Rewrite `frontend/tests/mocks/handlers.ts`:

```typescript
import { http, HttpResponse } from "msw";
import {
  mockUser,
  mockAlbum,
  mockMedia,
  mockStep,
  mockSteps,
  mockSegmentOutlines,
} from "../fixtures/mocks";

export const BASE = "http://localhost:8000/api/v1";

// Re-export for tests that need to reference mock data directly
export { mockUser as defaultUser, mockAlbum as defaultAlbum, mockMedia as defaultMedia, mockSteps as defaultSteps, mockSegmentOutlines as defaultSegmentOutlines } from "../fixtures/mocks";

export const handlers = [
  http.get(`${BASE}/users`, () => HttpResponse.json(mockUser)),
  http.patch(`${BASE}/users`, () => HttpResponse.json(mockUser)),
  http.get(`${BASE}/albums/:aid`, () => HttpResponse.json(mockAlbum)),
  http.patch(`${BASE}/albums/:aid`, () => HttpResponse.json(mockAlbum)),
  http.get(`${BASE}/albums/:aid/media`, () => HttpResponse.json(mockMedia)),
  http.get(`${BASE}/albums/:aid/steps`, () => HttpResponse.json(mockSteps)),
  http.get(`${BASE}/albums/:aid/segments`, () => HttpResponse.json(mockSegmentOutlines)),
  http.patch(`${BASE}/albums/:aid/steps/:sid`, () => HttpResponse.json(mockStep)),
];
```

- [ ] **Step 3: Update e2e/fixtures.ts to import from shared mocks**

Rewrite `frontend/e2e/fixtures.ts`:

```typescript
import { test as base, type Page } from "@playwright/test";
import {
  mockUser,
  mockAlbum,
  mockStep,
  mockSteps,
  mockSegmentOutlines,
  TINY_JPEG_BASE64,
} from "../tests/fixtures/mocks";

const API = "**/api/v1";

async function mockAllApi(page: Page) {
  await page.route(`${API}/users`, (route) =>
    route.fulfill({ json: mockUser }),
  );
  await page.route(`${API}/albums/**`, (route) => {
    const url = route.request().url();
    if (url.endsWith("/data")) {
      return route.fulfill({ json: { steps: mockSteps, segments: mockSegmentOutlines } });
    }
    return route.fulfill({ json: mockAlbum });
  });
  await page.route(`${API}/auth/google`, (route) =>
    route.fulfill({ json: mockUser }),
  );
  await page.route("**/media/**", (route) =>
    route.fulfill({
      contentType: "image/jpeg",
      body: Buffer.from(TINY_JPEG_BASE64, "base64"),
    }),
  );
}

export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    await mockAllApi(page);
    await page.addInitScript(() =>
      localStorage.setItem("last-album-id", "aid-1"),
    );
    await use(page);
  },
});

export { expect } from "@playwright/test";
```

- [ ] **Step 4: Run frontend unit tests**

```bash
cd frontend && bun run test
```

Expected: all pass

- [ ] **Step 5: Run E2E tests**

```bash
cd frontend && bun run test:e2e
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add frontend/tests/fixtures/mocks.ts frontend/tests/mocks/handlers.ts frontend/e2e/fixtures.ts
git commit -m "refactor: extract shared mock data to tests/fixtures/mocks.ts"
```

---

### Task 10: Move Mapbox Mock to Vitest Auto-Mock Location

Move the mapbox-gl mock from inline in `setup.ts` to Vitest's `__mocks__/` convention.

**Files:**
- Create: `frontend/tests/__mocks__/mapbox-gl.ts`
- Modify: `frontend/tests/setup.ts`
- Modify: `frontend/vitest.config.ts` (if needed for mock path)

- [ ] **Step 1: Create the auto-mock file**

Create `frontend/tests/__mocks__/mapbox-gl.ts`:

```typescript
import { vi } from "vitest";

const mapOn = vi.fn();

const Map = vi.fn(() => ({
  on: mapOn,
  off: vi.fn(),
  once: vi.fn(),
  remove: vi.fn(),
  addControl: vi.fn(),
  removeControl: vi.fn(),
  addSource: vi.fn(),
  removeSource: vi.fn(),
  addLayer: vi.fn(),
  removeLayer: vi.fn(),
  getSource: vi.fn(),
  getLayer: vi.fn(),
  setLayoutProperty: vi.fn(),
  setPaintProperty: vi.fn(),
  flyTo: vi.fn(),
  fitBounds: vi.fn(),
  resize: vi.fn(),
  getCanvas: vi.fn(() => ({ style: {} })),
  getContainer: vi.fn(() => document.createElement("div")),
  loaded: vi.fn(() => true),
  isStyleLoaded: vi.fn(() => true),
}));

const NavigationControl = vi.fn();

const Marker = vi.fn(() => ({
  setLngLat: vi.fn().mockReturnThis(),
  addTo: vi.fn().mockReturnThis(),
  remove: vi.fn(),
  getElement: vi.fn(() => document.createElement("div")),
  getLngLat: vi.fn(() => ({ lng: 0, lat: 0 })),
  on: vi.fn().mockReturnThis(),
  setDraggable: vi.fn().mockReturnThis(),
}));

const Popup = vi.fn(() => ({
  setLngLat: vi.fn().mockReturnThis(),
  setHTML: vi.fn().mockReturnThis(),
  addTo: vi.fn().mockReturnThis(),
  remove: vi.fn(),
}));

export default { Map, NavigationControl, Marker, Popup, supported: () => true };
```

- [ ] **Step 2: Remove the inline mock from setup.ts**

Remove the entire `vi.mock("mapbox-gl", ...)` block (lines 5-47) from `frontend/tests/setup.ts`. Vitest will auto-discover the `__mocks__/mapbox-gl.ts` file. Keep the `vi.mock("mapbox-gl")` call but without the factory — Vitest will use the `__mocks__` file:

```typescript
vi.mock("mapbox-gl");
```

- [ ] **Step 3: Run frontend tests**

```bash
cd frontend && bun run test
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/__mocks__/mapbox-gl.ts frontend/tests/setup.ts
git commit -m "refactor: move mapbox-gl mock to __mocks__/ auto-mock convention"
```

---

### Task 11: Restructure E2E Test Directories

Split E2E tests into `fast/` (mocked API) and `full/` (real backend) suites. Move existing tests to `fast/`. Set up Playwright config for both.

**Files:**
- Create: `frontend/e2e/fast/smoke.test.ts`
- Create: `frontend/e2e/fast/navigation.test.ts`
- Delete: `frontend/e2e/smoke.test.ts`
- Delete: `frontend/e2e/editor.test.ts`
- Modify: `frontend/e2e/fixtures.ts`
- Modify: `frontend/playwright.config.ts`
- Modify: `frontend/package.json` (update test:e2e script)

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p frontend/e2e/fast frontend/e2e/full
```

- [ ] **Step 2: Move existing smoke tests to fast/**

Move `frontend/e2e/smoke.test.ts` to `frontend/e2e/fast/smoke.test.ts`. Update the import path:

```typescript
import { test, expect } from "../fixtures";
```

- [ ] **Step 3: Move editor tests to fast/navigation.test.ts**

Move `frontend/e2e/editor.test.ts` to `frontend/e2e/fast/navigation.test.ts`. Update the import path:

```typescript
import { test, expect } from "../fixtures";
```

- [ ] **Step 4: Delete old files**

```bash
rm frontend/e2e/smoke.test.ts frontend/e2e/editor.test.ts
```

- [ ] **Step 5: Update playwright.config.ts for both suites**

```typescript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "fast",
      testDir: "./e2e/fast",
      use: { browserName: "chromium" },
    },
    {
      name: "full",
      testDir: "./e2e/full",
      use: { browserName: "chromium" },
    },
  ],
  webServer: {
    command: "bun run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
```

- [ ] **Step 6: Update package.json test:e2e scripts**

In `frontend/package.json`, update the e2e test scripts:

```json
"test:e2e": "playwright test --project=fast",
"test:e2e:full": "playwright test --project=full"
```

- [ ] **Step 7: Run fast E2E tests**

```bash
cd frontend && bun run test:e2e
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add frontend/e2e/ frontend/playwright.config.ts frontend/package.json
git commit -m "refactor: split E2E tests into fast (mocked) and full (real backend) suites"
```

---

### Task 12: Audit and Clean Up Existing Tests

Review existing tests against the testing philosophy. Remove tests that test library behavior. Identify shallow tests that don't verify behavior.

**Files:**
- Modify: various test files (determined during audit)

- [ ] **Step 1: Audit backend tests**

Read each test file and check:
1. Does it test project behavior or library behavior?
2. Does it test implementation details or outcomes?
3. Does it have duplicated helpers that should use factories?

Known issues from spec review:
- `test_pipeline.py` was addressed in Task 7
- `test_segments.py` integration tests were addressed in Task 6
- Check for other `make_points()` duplicates

Run: `grep -rn "def _make_points\|def make_points" backend/tests/`

- [ ] **Step 2: Audit frontend tests**

Read each test file in `frontend/tests/` and check:
1. Are there "renders without error" tests that don't assert anything meaningful?
2. Are there tests that just verify a mock was called (testing wiring, not behavior)?

Review specifically:
- `tests/components/` — component tests should verify rendered output or user interaction results
- `tests/composables/` — composable tests should verify state changes and return values

- [ ] **Step 3: Fix issues found**

For each issue:
- Remove tests that test library behavior
- Remove shallow tests that just assert "component exists"
- Replace implementation-detail tests with behavior tests
- Fix duplicated helpers to use factories

- [ ] **Step 4: Run all tests**

```bash
cd backend && uv run pytest -x -q
cd frontend && bun run test
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: clean up tests per testing philosophy audit"
```

---

### Task 13: Delete Old test_data Directory

Now that everything points to `fixtures/trips/`, remove the old untracked 4.7GB directory.

**Files:**
- Delete: `backend/tests/test_data/` (untracked, not in git)

- [ ] **Step 1: Verify no remaining references**

```bash
grep -rn "test_data" backend/tests/ --include="*.py"
```

Expected: no results (all references were updated in previous tasks)

- [ ] **Step 2: Run all backend tests one more time**

```bash
cd backend && uv run pytest -x -q
```

Expected: all pass

- [ ] **Step 3: Delete the directory**

```bash
rm -rf backend/tests/test_data/
```

- [ ] **Step 4: Verify disk space recovered**

```bash
du -sh backend/tests/
```

Expected: should be a few KB (just .py files and snapshots)

> **Note:** This directory was never tracked in git, so no git commit is needed. The deletion is purely local cleanup.

---

### Task 14: Update mise.toml for E2E Test Variants

Add the full E2E test task to mise.toml.

**Files:**
- Modify: `mise.toml`

- [ ] **Step 1: Add full E2E task**

Add after the existing `test:e2e` task:

```toml
[tasks."test:e2e:full"]
description = "Run full E2E tests (real backend, pre-merge)"
dir = "frontend"
run = "bun run test:e2e:full"
```

- [ ] **Step 2: Commit**

```bash
git add mise.toml
git commit -m "chore: add mise task for full E2E test suite"
```

---

### Task 15: Final Verification

Run the complete test suite to verify everything works together.

**Files:** None (verification only)

- [ ] **Step 1: Run backend tests**

```bash
cd backend && uv run pytest -v
```

Expected: all pass

- [ ] **Step 2: Run frontend unit tests**

```bash
cd frontend && bun run test
```

Expected: all pass

- [ ] **Step 3: Run fast E2E tests**

```bash
cd frontend && bun run test:e2e
```

Expected: all pass

- [ ] **Step 4: Run linters**

```bash
mise run lint
```

Expected: all pass

- [ ] **Step 5: Final commit if any adjustments were needed**

```bash
git add -A
git commit -m "fix: address issues found during final verification"
```

---

## Follow-Up Work (Not In This Plan)

These items depend on manual steps or are large enough to warrant their own plan:

1. **Curate demo trip data** (manual): Select 5-8 steps from the SA trip, pick ~30 landscape/animal photos, create subset trip.json/locations.json, add to `fixtures/demo/` via Git LFS.

2. **Write full E2E interaction tests**: Once the demo trip exists, write Playwright tests in `e2e/full/` for drag-drop photo reorder, photo focus/unfocus, scroll-to-step, undo/redo, segment boundary drag. These require a real running backend seeded with demo data.

3. **Set up full E2E backend infrastructure**: Docker Compose or webServer config that starts the real FastAPI backend + database for the `full` Playwright project. Includes DB seeding fixtures.

4. **Migrate external HTTP mocks to pytest-httpx**: Replace manual `patch()` calls for Mapbox and OpenMeteo service tests with pytest-httpx request/response recording. This is incremental — do it as those test files are touched.
